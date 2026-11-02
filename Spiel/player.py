from ursina import Entity, Color, lerp, time
from constants import (
    LANES, LANE_COUNT,
    JUMP_VEL, GRAVITY, SLIDE_DUR, SLIDE_HOLD_REFRESH, FAST_DROP_VEL, LANE_SPD,
    PLAYER_BASE_Y, PLAYER_SY, PLAYER_HW, PLAYER_HH,
    PUSHBACK_DUR, PUSHBACK_DIST, RAMP_STEP_MAX,
)
from game_state import GS
from powerups import POWERS, GLIDE_GRAVITY_UP, GLIDE_GRAVITY_DOWN


class Player(Entity):
    """
    Spielercharakter mit Sprung, Slide, Spurwechsel, Pushback, Rampen und Power-ups.

    Öffentliches Interface (Tastatur ODER Gestenmodul):
        action_left()   action_right()   set_lane(n)
        action_jump()   action_slide()   start_slide() / stop_slide()  (Taste)
                                         hold_slide() / release_slide() (Kamera)
        activate_power(name)

    Nach Erstellung muss obstacles_ref auf die globale Hindernisliste zeigen:
        player.obstacles_ref = obstacles
    """

    def __init__(self, state, x_offset=0.0, marker_color=None):
        super().__init__(
            model=None,
            scale=(0.7, PLAYER_SY, 0.7),
            position=(x_offset, PLAYER_BASE_Y, 0),
        )
        # Spielerabhängiger Zustand (Punkte/Leben/Unverwundbarkeit/alive).
        self.state         = state
        # Seitlicher Versatz innerhalb der Spur (damit sich zwei Spieler in
        # derselben Spur nicht komplett überdecken).
        self.x_offset      = x_offset
        self.lane          = 1
        self.target_x      = LANES[1] + x_offset
        self.vel_y         = 0.0
        self.is_jumping    = False
        self.is_sliding    = False
        self.slide_held    = False
        self.slide_timer   = 0.0
        # In der Luft gedrücktes Ducken: startet bei der Landung (held = Taste gehalten)
        self._slide_queued      = False
        self._slide_queued_held = False
        # Per OSC gewünschte Spur, die gerade nicht erreichbar ist (Zug im Weg,
        # Zurückstoßen) – wird übernommen, sobald es geht
        self.pending_lane  = None
        self._base_sy      = PLAYER_SY
        self._base_y       = PLAYER_BASE_Y
        self.platform      = None
        self.ramp          = None    # Zug, dessen Rampe der Spieler gerade hochläuft
        # Ducken per Kamera: verbleibende Zeit, bis das Halten ohne neue Meldung endet
        # (None = kein Kamera-Halten, z.B. Taste gedrückt)
        self._hold_left    = None
        self._pb_timer     = 0.0
        self.obstacles_ref = []
        self._planes       = []   # alle visuellen Quad-Entities

        # Atlas-Layout (3 Spalten × 2 Zeilen, v=0 unten):
        #   obere Reihe:  [f (-Z, Kamera)] [b (+Z, Laufrichtung)] [r (+X)]
        #   untere Reihe: [l (-X)]         [t (+Y oben)]          [bot (-Y unten)]
        UV = {
            'f':   (0,    0.5),
            'b':   (1/3,  0.5),
            'r':   (2/3,  0.5),
            'l':   (0,    0),
            't':   (1/3,  0),
            'bot': (2/3,  0),
        }

        def _box(cx, cy, cz, W, H, D, atlas):
            """6 Quads (je 1 pro Seite) als Kinder, aus einem 3×2 Atlas."""
            hw, hh, hd = W/2, H/2, D/2
            for key, (ox, oy, oz), rot, sw, sh in (
                ('f',   ( 0,    0,  -hd), (  0,   0, 0), W, H),  # -Z, Kamera-Seite
                ('b',   ( 0,    0,   hd), (  0, 180, 0), W, H),  # +Z, Laufrichtung
                ('l',   (-hw,   0,    0), (  0,  90, 0), D, H),  # -X links
                ('r',   ( hw,   0,    0), (  0, -90, 0), D, H),  # +X rechts
                ('t',   ( 0,   hh,    0), (-90,   0, 0), W, D),  # +Y oben
                ('bot', ( 0,  -hh,    0), ( 90,   0, 0), W, D),  # -Y unten
            ):
                u, v = UV[key]
                self._planes.append(Entity(
                    parent=self, model='quad', double_sided=True,
                    texture=atlas,
                    texture_scale=(1/3, 0.5),
                    texture_offset=(u, v),
                    position=(cx + ox, cy + oy, cz + oz),
                    rotation=rot, scale=(sw, sh, 1),
                ))

        _box(0,     0.04,   0,    0.80, 0.33, 0.50, 'textures/01_torso.png')
        _box(0,     0.34,   0,    0.60, 0.28, 0.60, 'textures/02_head.png')
        _box(-0.20, -0.28,  0,    0.37, 0.31, 0.40, 'textures/03_legs.png')
        _box(+0.20, -0.28,  0,    0.37, 0.31, 0.40, 'textures/03_legs.png')
        _box(0,     0.04,  -0.35, 0.55, 0.28, 0.20, 'textures/04_backpack.png')

        # Signalfarben-Marker zur Unterscheidung der Spieler (leuchtender
        # Diamant über dem Kopf + Boden-Ring unter den Füßen).
        self.marker_color = marker_color
        if marker_color is not None:
            from ursina import Entity as _E
            self.beacon = _E(parent=self, model='cube', color=marker_color,
                             unlit=True, scale=(0.16, 0.16, 0.16),
                             position=(0, 0.62, 0), rotation=(45, 45, 0))
            self.ring = _E(parent=self, model='circle', color=marker_color,
                           unlit=True, double_sided=True, scale=1.3,
                           rotation=(90, 0, 0), position=(0, -0.72, 0))

        # Power-up-Effekte: Schild-Blase, Flügel beim Gleiten, Magnet über dem Kopf
        self.shield_fx = Entity(parent=self, model='sphere', color=Color(0.35, 0.85, 1.0, 0.3),
                                unlit=True, double_sided=True, enabled=False)
        self.wings_fx = [Entity(parent=self, model='quad', color=Color(0.95, 0.97, 1.0, 0.85),
                                unlit=True, double_sided=True, enabled=False,
                                position=(side * 1.0, 0.1, 0.05), rotation=(0, 0, side * -14),
                                scale=(1.1, 0.3, 1))
                         for side in (-1, 1)]
        self.magnet_fx = Entity(parent=self, model='quad', texture=POWERS['magnet'].icon,
                                billboard=True, unlit=True, enabled=False,
                                position=(0, 0.95, 0), scale=(0.5 / 0.7, 0.5, 1))

    # ── Öffentliches Interface ────────────────────────────────────────

    def _lane_x(self, lane: int) -> float:
        return LANES[lane] + self.x_offset

    def set_lane(self, lane: int):
        """Setzt die Zielspur direkt (für positionsbasierte Steuerung via OSC).

        Ist der Weg gerade nicht frei (Zug auf der Zielspur oder dazwischen,
        Zurückstoßen), merkt sich der Spieler die Spur und wechselt, sobald es
        geht – oder bis ein neuer Spur-Befehl kommt. Wichtig für Sprache: die
        sendet jeden Befehl nur einmal, er ging früher einfach verloren.
        """
        self.pending_lane = lane
        self._apply_pending_lane()

    def action_left(self):
        self.pending_lane = None     # Tastatur steuert relativ – keine gemerkte Spur
        if self._pb_timer > 0:
            return
        if self.lane > 0 and self._lane_passable(self.lane - 1):
            self.lane    -= 1
            self.target_x = self._lane_x(self.lane)

    def action_right(self):
        self.pending_lane = None
        if self._pb_timer > 0:
            return
        if self.lane < LANE_COUNT - 1 and self._lane_passable(self.lane + 1):
            self.lane    += 1
            self.target_x = self._lane_x(self.lane)

    def action_jump(self):
        if self._pb_timer > 0:
            return
        # Sprung vom Boden ODER von einem Bus-/Zug-Dach (Plattform).
        # Steht der Spieler auf einer Plattform, ist is_jumping zwar False,
        # aber die Plattform-Bindung muss gelöst werden, damit er sauber
        # abhebt und auf eine andere Plattform hüpfen kann.
        if self.is_jumping and self.platform is None:
            return                       # schon in der Luft
        # Sprung aus dem Ducken: sofort aufstehen und abspringen
        # (früher wurde der Sprung hier verworfen – und das Ducken trotzdem beendet)
        if self.is_sliding:
            self._end_slide()
        self.vel_y      = JUMP_VEL
        self.is_jumping = True
        self.platform   = None
        self.ramp       = None

    def action_slide(self):
        """Einmaliger Slide (für OSC/Kamera): läuft nach SLIDE_DUR automatisch aus.
        In der Luft: schnell nach unten fallen und bei der Landung ducken."""
        if self._pb_timer > 0:
            return
        if self.is_jumping:
            self._queue_slide(held=False)
        elif not self.is_sliding:
            self._begin_slide(held=False)

    def start_slide(self):
        """Slide beginnen und halten (Taste gedrückt halten). Endet erst bei stop_slide().
        In der Luft: schnell nach unten fallen, Slide startet bei der Landung."""
        if self._pb_timer > 0:
            return
        self._hold_left = None          # Taste hält, bis sie losgelassen wird
        if self.is_jumping:
            self._queue_slide(held=True)
        elif not self.is_sliding:
            self._begin_slide(held=True)
        else:
            self.slide_held  = True
            self.slide_timer = SLIDE_DUR

    def stop_slide(self):
        """Slide sofort beenden (Taste losgelassen)."""
        self.slide_held  = False
        self.slide_timer = 0.0
        # Taste schon vor der Landung losgelassen → kein Slide mehr bei der Landung
        if self._slide_queued and self._slide_queued_held:
            self._slide_queued = False

    def hold_slide(self):
        """Ducken per Kamera – kommt wiederholt, solange der Spieler geduckt ist.
        Die Figur rutscht, solange er unten bleibt, mindestens aber SLIDE_DUR.
        Bleibt die Meldung SLIDE_HOLD_REFRESH lang aus, endet das Halten von selbst.
        In der Luft: schnell nach unten fallen, Slide startet bei der Landung."""
        if self._pb_timer > 0:
            return
        if self.is_jumping:
            if not self._slide_queued:
                self._queue_slide(held=True)
            self._slide_queued_held = True
        elif not self.is_sliding:
            self._begin_slide(held=True)
        else:
            self.slide_held = True      # Mindestdauer zählt ab dem Abtauchen weiter
        self._hold_left = SLIDE_HOLD_REFRESH

    def release_slide(self):
        """Spieler steht wieder auf (Kamera): Der Slide läuft noch bis SLIDE_DUR aus."""
        self._release_hold()

    def activate_power(self, name: str) -> bool:
        """Power-up auslösen (Kamera-Haltung oder Taste). False, wenn Power-ups
        abgeschaltet sind, es noch abklingt oder gerade nicht geht."""
        if not GS.powerups or not self.state.alive or name not in POWERS:
            return False
        if name == 'glide' and self._pb_timer > 0:
            return False                # beim Zurückstoßen gibt es keinen Sprung
        if not self.state.powers.activate(name):
            return False
        if name == 'glide':
            self._start_glide()
        return True

    def action_stand(self):
        """Neutralpose-Signal (für Gestensteuerung).

        Reale Bewegungen sind kürzer als die in-Game-Animationen:
        Slide ist zeitbasiert (SLIDE_DUR), Sprung impulsbasiert. Beide laufen
        immer vollständig durch. Diese Methode bricht sie deshalb NICHT mehr ab –
        ein nachfolgendes /game/stand vom Sender wird absichtlich ignoriert,
        damit ein voller Spielsprung / 1.5 s Slide stattfindet.
        """
        return

    def pushback(self):
        """Startet die Zurückzieh-Animation nach einer Kollision."""
        self._pb_timer     = PUSHBACK_DUR
        self._slide_queued = False   # während des Zurückstoßens wird nicht geduckt

    # ── Hilfsmethoden ─────────────────────────────────────────────────

    def _begin_slide(self, held: bool):
        self.is_sliding  = True
        self.slide_held  = held
        self.slide_timer = SLIDE_DUR
        self.scale_y     = self._base_sy * 0.45
        self.y           = self._slide_y()

    def _end_slide(self):
        self.is_sliding  = False
        self.slide_held  = False
        self.slide_timer = 0.0
        self._hold_left  = None
        self.scale_y     = self._base_sy
        # In der Luft (geduckt vom Dach gefallen) nicht auf den Boden setzen –
        # der Fall läuft normal weiter
        if not self.is_jumping:
            self.y = self._floor()

    def _queue_slide(self, held: bool):
        """Ducken in der Luft: sofort schnell nach unten (wie bei Subway Surfers),
        der Slide selbst startet bei der Landung (Boden oder Dach)."""
        self._slide_queued      = True
        self._slide_queued_held = held
        self.vel_y = min(self.vel_y, -FAST_DROP_VEL)

    def _release_hold(self):
        self.slide_held         = False
        self._slide_queued_held = False
        self._hold_left         = None

    def _start_glide(self):
        """Gleitsprung: vom Boden, Dach oder der Rampe ab. In der Luft gibt es kurz
        Auftrieb. Die geringere Schwerkraft liefert _gravity(), solange es wirkt."""
        if self.is_sliding:
            self._end_slide()
        self._slide_queued = False
        if self.is_jumping:
            self.vel_y = max(self.vel_y, JUMP_VEL * 0.5)
        else:
            self.vel_y      = JUMP_VEL
            self.is_jumping = True
            self.platform   = None
            self.ramp       = None

    def _gravity(self) -> float:
        """Schwerkraft – beim Gleiten schwächer: steigt höher und sinkt langsam."""
        if self.state.powers.is_active('glide'):
            return GRAVITY * (GLIDE_GRAVITY_UP if self.vel_y > 0 else GLIDE_GRAVITY_DOWN)
        return GRAVITY

    def _apply_pending_lane(self):
        """Gemerkte Zielspur übernehmen, sobald möglich: nicht während des
        Zurückstoßens und nur, wenn alle Spuren auf dem Weg frei sind – sonst
        würde der Spieler bei links→rechts durch einen Zug in der Mitte laufen."""
        lane = self.pending_lane
        if lane is None:
            return
        if lane == self.lane:
            self.pending_lane = None
            return
        if self._pb_timer > 0:
            return
        step = 1 if lane > self.lane else -1
        for l in range(self.lane + step, lane + step, step):
            if not self._lane_passable(l):
                return
        self.lane         = lane
        self.target_x     = self._lane_x(lane)
        self.pending_lane = None

    def _lane_passable(self, lane_idx: int) -> bool:
        """
        Prüft ob eine Spur frei von Zügen ist.
        Verhindert das seitliche Einlaufen in einen Zug (Wandeffekt).
        """
        target_x = LANES[lane_idx]
        for o in self.obstacles_ref:
            if o._dead or o.kind != 'train':
                continue
            if abs(o.x - target_x) >= o.hw + PLAYER_HW + 0.15:
                continue
            if abs(o.z - self.z) < o.hz + 2.0:
                return False
            # Rampe davor: seitlich nur betretbar, solange sie noch flach ist
            surface = o.ramp_surface(self.z)
            if surface is not None and surface > RAMP_STEP_MAX:
                return False
        return True

    def half_extents(self):
        return PLAYER_HW, self.scale_y * PLAYER_HH

    def _platform_top(self):
        """Oberkante der Plattform (Zug- oder Autodach), auf der der Spieler steht – sonst None."""
        # `is not None` statt Wahrheitswert: ein zerstörtes Ursina-Entity ist "falsy"
        if self.platform is not None and not self.platform._dead:
            return self.platform.y + self.platform.hh
        return None

    def _ramp_under(self):
        """(Zug, Höhe) der Rampe direkt unter dem Spieler – oder None."""
        found = None
        for o in self.obstacles_ref:
            if o._dead or not o.ramp_len or abs(o.x - self.x) >= o.hw:
                continue
            surface = o.ramp_surface(self.z)
            if surface is not None and (found is None or surface > found[1]):
                found = (o, surface)
        return found

    def _support_top(self):
        """Oberkante unter dem Spieler: Dach (Plattform) oder Rampe – None = Boden."""
        top = self._platform_top()
        if top is not None:
            return top
        ramp = self._ramp_under()
        return ramp[1] if ramp is not None else None

    def _rest_y(self, top, sliding: bool) -> float:
        """Mittelpunkt-Höhe auf einer Fläche mit Oberkante `top` (None = Boden),
        stehend oder geduckt – gleiche Formel wie bei der Landung auf einem Dach."""
        ground = self._base_y - self._base_sy * 0.27 if sliding else self._base_y
        if top is None:
            return ground
        return max(ground, top + self.scale_y * PLAYER_HH)

    def _floor(self) -> float:
        """Mittelpunkt-Höhe im Stand: auf dem Dach, auf der Rampe oder am Boden."""
        return self._rest_y(self._support_top(), sliding=False)

    def _slide_y(self) -> float:
        """Mittelpunkt-Höhe geduckt. Auf einem Dach oder einer Rampe bleibt der Spieler
        oben, statt auf Bodenhöhe in den Zug/das Auto zu rutschen (= Treffer)."""
        return self._rest_y(self._support_top(), sliding=True)

    def _leave_ramp(self):
        """Rampe zu Ende: oben angekommen → aufs Zugdach, seitlich runter → fallen."""
        o, self.ramp = self.ramp, None
        if (not o._dead and o.front_z <= self.z + 0.5
                and abs(o.x - self.x) < o.hw + PLAYER_HW and o.z_overlaps(self.z, 0.0)):
            self.platform = o
            self.y = self._rest_y(o.roof_y, self.is_sliding)
        else:
            self.vel_y      = 0.0
            self.is_jumping = True

    def _update_fx(self):
        """Power-up-Effekte ein-/ausblenden (Schild blinkt kurz vor dem Ende)."""
        p = self.state.powers
        left = p.active['shield']
        self.shield_fx.enabled = left > 1.5 or (left > 0 and int(left * 6) % 2 == 0)
        if self.shield_fx.enabled:
            # Kugel trotz gestauchter Figur (Ducken) rund halten
            self.shield_fx.scale = (1.7 / self.scale_x, 1.7 / self.scale_y, 1.7 / self.scale_z)
        gliding = p.is_active('glide') and self.is_jumping
        for wing in self.wings_fx:
            wing.enabled = gliding
        self.magnet_fx.enabled = p.is_active('magnet')

    # ── Update (Physik) ───────────────────────────────────────────────

    def update(self):
        if not GS.running or GS.paused or not self.state.alive:
            return
        dt = time.dt

        # Blinken bei Unverwundbarkeit
        self.visible = (int(self.state.inv_timer * 8) % 2 == 0) if self.state.is_invincible() else True

        # ── Ducken per Kamera: ohne neue Meldung endet das Halten ─────
        if self._hold_left is not None:
            self._hold_left -= dt
            if self._hold_left <= 0:
                self._release_hold()

        # ── Pushback-Z-Animation ──────────────────────────────────────
        if self._pb_timer > 0:
            self._pb_timer -= dt
            t = 1.0 - self._pb_timer / PUSHBACK_DUR   # 0 → 1
            if t < 0.3:
                self.z = -PUSHBACK_DIST * (t / 0.3)         # schnell zurück
            else:
                self.z = -PUSHBACK_DIST * (1.0 - (t - 0.3) / 0.7)  # langsam vor
        else:
            self.z = 0.0

        # ── Gemerkte Spur (OSC) übernehmen, sobald der Weg frei ist ───
        self._apply_pending_lane()

        # ── Seitliche Bewegung ────────────────────────────────────────
        self.x = lerp(self.x, self.target_x, min(LANE_SPD * dt, 1))

        # ── Plattform-Exit: hinten runtergefahren oder Spur verlassen ─
        # WICHTIG: Hinterkante (z + hz) prüfen, nicht die Vorderkante –
        # sonst fällt der Spieler direkt nach dem Aufsteigen wieder runter
        # und kann nie vom Dach abspringen.
        # WICHTIG: `is not None` statt `if self.platform:` – ein zerstörtes
        # Ursina-Entity (leerer NodePath) ist "falsy". Sonst wurde dieser Block
        # übersprungen und der Spieler schwebte nach dem Despawn in der Luft.
        # _dead zuerst prüfen: Position eines zerstörten Entities nicht mehr lesen.
        if self.platform is not None:
            p = self.platform
            if (p._dead
                    or (p.z + p.hz) < self.z                   # ganzer Zug hinten vorbei
                    or abs(p.x - self.x) > p.hw + PLAYER_HW):  # Spur gewechselt, kein Dach drunter
                self.platform = None
                if not self.is_jumping:
                    self.vel_y      = 0.0
                    self.is_jumping = True   # Spieler fällt vom Zug

        # ── Rampe: der Boden steigt unter den Füßen an ────────────────
        # Oben angekommen geht es aufs Zugdach, seitlich runter heißt fallen
        if self.platform is None and not self.is_jumping:
            ramp = self._ramp_under()
            if ramp is not None:
                self.ramp = ramp[0]
                self.y    = self._rest_y(ramp[1], self.is_sliding)
            elif self.ramp is not None:
                self._leave_ramp()

        # ── Sprung-Physik ─────────────────────────────────────────────
        # Landung nur wenn FALLEND (vel_y <= 0) und auf/unter Boden bzw. Rampe
        if self.is_jumping:
            self.vel_y += self._gravity() * dt
            self.y     += self.vel_y * dt
            if self.vel_y <= 0:
                ramp = self._ramp_under()
                top  = ramp[1] if ramp is not None else None
                if self.y <= self._rest_y(top, sliding=False):
                    # Geduckt vom Dach gefallen → geduckt landen, nicht schweben
                    self.y          = self._rest_y(top, self.is_sliding)
                    self.vel_y      = 0.0
                    self.is_jumping = False
                    self.platform   = None
                    self.ramp       = ramp[0] if ramp is not None else None

        # ── In der Luft gedrücktes Ducken bei der Landung starten ─────
        # (Landung auf dem Boden: oben; auf einem Dach: in _check_collisions)
        if self._slide_queued and not self.is_jumping:
            self._slide_queued = False
            if not self.is_sliding:
                self._begin_slide(held=self._slide_queued_held)

        # ── Slide-Timer ───────────────────────────────────────────────
        # Läuft immer mit, der Slide endet aber erst, wenn er nicht mehr gehalten
        # wird (Taste / Kamera) – gehalten dauert er also mindestens SLIDE_DUR.
        if self.is_sliding:
            self.slide_timer -= dt
            if self.slide_timer <= 0 and not self.slide_held:
                self._end_slide()

        self._update_fx()

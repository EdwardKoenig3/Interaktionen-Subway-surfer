from ursina import Entity, lerp, time
from constants import (
    LANES, LANE_COUNT,
    JUMP_VEL, GRAVITY, SLIDE_DUR, LANE_SPD,
    PLAYER_BASE_Y, PLAYER_SY, PLAYER_HW, PLAYER_HH,
    PUSHBACK_DUR, PUSHBACK_DIST,
)
from game_state import GS


class Player(Entity):
    """
    Spielercharakter mit Sprung, Slide, Spurwechsel und Pushback.

    Öffentliches Interface (Tastatur ODER Gestenmodul):
        action_left()   action_right()
        action_jump()   action_slide()

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
        self._base_sy      = PLAYER_SY
        self._base_y       = PLAYER_BASE_Y
        self.platform      = None
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

    # ── Öffentliches Interface ────────────────────────────────────────

    def _lane_x(self, lane: int) -> float:
        return LANES[lane] + self.x_offset

    def set_lane(self, lane: int):
        """Setzt die Zielspur direkt (für positionsbasierte Steuerung via OSC).

        Alle Spuren auf dem Weg müssen frei sein – sonst würde der Spieler
        bei links→rechts durch einen Zug in der Mitte laufen. Der Sender
        wiederholt die Position, der Wechsel klappt also, sobald der Weg frei ist.
        """
        if self._pb_timer > 0 or lane == self.lane:
            return
        step = 1 if lane > self.lane else -1
        for l in range(self.lane + step, lane + step, step):
            if not self._lane_passable(l):
                return
        self.lane     = lane
        self.target_x = self._lane_x(lane)

    def action_left(self):
        if self._pb_timer > 0:
            return
        if self.lane > 0 and self._lane_passable(self.lane - 1):
            self.lane    -= 1
            self.target_x = self._lane_x(self.lane)

    def action_right(self):
        if self._pb_timer > 0:
            return
        if self.lane < LANE_COUNT - 1 and self._lane_passable(self.lane + 1):
            self.lane    += 1
            self.target_x = self._lane_x(self.lane)

    def action_jump(self):
        if self._pb_timer > 0:
            return
        if self.is_sliding:
            return
        # Sprung vom Boden ODER von einem Bus-/Zug-Dach (Plattform).
        # Steht der Spieler auf einer Plattform, ist is_jumping zwar False,
        # aber die Plattform-Bindung muss gelöst werden, damit er sauber
        # abhebt und auf eine andere Plattform hüpfen kann.
        if not self.is_jumping or self.platform is not None:
            self.vel_y      = JUMP_VEL
            self.is_jumping = True
            self.platform   = None

    def action_slide(self):
        """Einmaliger Slide (für OSC/Kamera): läuft nach SLIDE_DUR automatisch aus."""
        if self._pb_timer > 0:
            return
        if not self.is_jumping and not self.is_sliding:
            self.is_sliding  = True
            self.slide_timer = SLIDE_DUR
            self.scale_y     = self._base_sy * 0.45
            self.y           = self._slide_y()

    def start_slide(self):
        """Slide beginnen und halten (Taste gedrückt halten). Endet erst bei stop_slide()."""
        if self._pb_timer > 0:
            return
        if not self.is_jumping:
            if not self.is_sliding:
                self.is_sliding = True
                self.scale_y    = self._base_sy * 0.45
                self.y          = self._slide_y()
            self.slide_held  = True
            self.slide_timer = SLIDE_DUR

    def stop_slide(self):
        """Slide sofort beenden (Taste losgelassen)."""
        self.slide_held  = False
        self.slide_timer = 0.0

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
        self._pb_timer = PUSHBACK_DUR

    # ── Hilfsmethoden ─────────────────────────────────────────────────

    def _lane_passable(self, lane_idx: int) -> bool:
        """
        Prüft ob eine Spur frei von Zügen ist.
        Verhindert das seitliche Einlaufen in einen Zug (Wandeffekt).
        """
        target_x = LANES[lane_idx]
        for o in self.obstacles_ref:
            if o._dead or o.kind != 'train':
                continue
            if abs(o.z - self.z) < o.hz + 2.0:
                if abs(o.x - target_x) < o.hw + PLAYER_HW + 0.15:
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

    def _floor(self) -> float:
        """Mittelpunkt-Höhe im Stand: auf dem Dach (gleiche Formel wie bei der Landung) oder Boden."""
        top = self._platform_top()
        if top is not None:
            return top + self.scale_y * PLAYER_HH
        return self._base_y

    def _slide_y(self) -> float:
        """Mittelpunkt-Höhe geduckt. Auf einem Dach bleibt der Spieler oben,
        statt auf Bodenhöhe in den Zug/das Auto zu rutschen (= Treffer)."""
        top = self._platform_top()
        if top is not None:
            return top + self.scale_y * PLAYER_HH
        return self._base_y - self._base_sy * 0.27

    # ── Update (Physik) ───────────────────────────────────────────────

    def update(self):
        if not GS.running or GS.paused or not self.state.alive:
            return
        dt = time.dt

        # Blinken bei Unverwundbarkeit
        self.visible = (int(self.state.inv_timer * 8) % 2 == 0) if self.state.is_invincible() else True

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

        # ── Sprung-Physik ─────────────────────────────────────────────
        # Landung nur wenn FALLEND (vel_y <= 0) und auf/unter Boden
        if self.is_jumping:
            self.vel_y += GRAVITY * dt
            self.y     += self.vel_y * dt
            if self.vel_y <= 0 and self.y <= self._base_y:
                # Geduckt vom Dach gefallen → geduckt landen, nicht schweben
                self.y          = self._slide_y() if self.is_sliding else self._base_y
                self.vel_y      = 0.0
                self.is_jumping = False
                self.platform   = None

        # ── Slide-Timer ───────────────────────────────────────────────
        # Wenn Taste gehalten (slide_held), läuft der Timer nicht ab.
        if self.is_sliding:
            if not self.slide_held:
                self.slide_timer -= dt
            if self.slide_timer <= 0:
                self.is_sliding  = False
                self.slide_held  = False
                self.scale_y     = self._base_sy
                self.y           = self._floor()

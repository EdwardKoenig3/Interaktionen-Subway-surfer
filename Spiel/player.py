import math
from ursina import Entity, lerp, time
from constants import (
    LANES, LANE_COUNT,
    JUMP_VEL, GRAVITY, SLIDE_DUR, LANE_SPD,
    PLAYER_BASE_Y, PLAYER_SY, PLAYER_HW, PLAYER_HH,
    TRAIN_TOP, RAMP_LEN,
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

    def __init__(self):
        super().__init__(
            model=None,
            scale=(0.7, PLAYER_SY, 0.7),
            position=(0, PLAYER_BASE_Y, 0),
        )
        self.lane          = 1
        self.target_x      = LANES[1]
        self.vel_y         = 0.0
        self.is_jumping    = False
        self.is_sliding    = False
        self.slide_held    = False
        self.slide_timer   = 0.0
        self._ramp_jump    = False
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

    # ── Öffentliches Interface ────────────────────────────────────────

    def set_lane(self, lane: int):
        """Setzt die Zielspur direkt (für positionsbasierte Steuerung via OSC)."""
        if self._pb_timer > 0 or lane == self.lane:
            return
        if self._lane_passable(lane):
            self.lane     = lane
            self.target_x = LANES[lane]

    def action_left(self):
        if self._pb_timer > 0:
            return
        if self.lane > 0 and self._lane_passable(self.lane - 1):
            self.lane    -= 1
            self.target_x = LANES[self.lane]

    def action_right(self):
        if self._pb_timer > 0:
            return
        if self.lane < LANE_COUNT - 1 and self._lane_passable(self.lane + 1):
            self.lane    += 1
            self.target_x = LANES[self.lane]

    def action_jump(self):
        if self._pb_timer > 0:
            return
        if not self.is_jumping and not self.is_sliding:
            self.vel_y      = JUMP_VEL
            self.is_jumping = True

    def action_slide(self):
        """Einmaliger Slide (für OSC/Kamera): läuft nach SLIDE_DUR automatisch aus."""
        if self._pb_timer > 0:
            return
        if not self.is_jumping and not self.is_sliding:
            self.is_sliding  = True
            self.slide_timer = SLIDE_DUR
            self.scale_y     = self._base_sy * 0.45
            self.y           = self._base_y - self._base_sy * 0.27

    def start_slide(self):
        """Slide beginnen und halten (Taste gedrückt halten). Endet erst bei stop_slide()."""
        if self._pb_timer > 0:
            return
        if not self.is_jumping:
            if not self.is_sliding:
                self.is_sliding = True
                self.scale_y    = self._base_sy * 0.45
                self.y          = self._base_y - self._base_sy * 0.27
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

    def _floor(self) -> float:
        """Bodenhöhe: Zugdach wenn auf Plattform, sonst Boden."""
        if self.platform and not self.platform._dead:
            return TRAIN_TOP + self.scale_y * 0.5
        return self._base_y

    # ── Update (Physik) ───────────────────────────────────────────────

    def update(self):
        if not GS.running:
            return
        dt = time.dt

        # Blinken bei Unverwundbarkeit
        self.visible = (int(GS.inv_timer * 8) % 2 == 0) if GS.is_invincible() else True

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

        # ── Rampen-Boost ──────────────────────────────────────────────
        # Wenn die Vorderkante eines Rampen-Zugs nahe ist, Spieler nach oben boosten.
        # Funktioniert in jedem Zustand (Laufen, Springen, Sliden):
        # die Treppe ist immer der Weg nach oben – kein Schaden, kein Phasen.
        if self.platform is None and not self._ramp_jump:
            for o in self.obstacles_ref:
                if o._dead or not o.has_ramp:
                    continue
                train_front = o.z - o.hz
                if 0.3 <= train_front <= RAMP_LEN + 0.8:
                    if abs(o.x - self.x) < o.hw + 0.35:
                        # Slide automatisch abbrechen, sonst startet der Sprung
                        # aus geduckter Pose und erreicht das Zugdach nicht.
                        if self.is_sliding:
                            self.is_sliding  = False
                            self.slide_held  = False
                            self.slide_timer = 0.0
                            self.scale_y     = self._base_sy
                            self.y           = self._base_y
                        target_top = TRAIN_TOP + self.scale_y * 0.5
                        v = math.sqrt(2 * abs(GRAVITY) * max(target_top - self.y, 0.1))
                        self.vel_y      = max(self.vel_y, v)
                        self.is_jumping = True
                        self._ramp_jump = True
                        break

        # ── Plattform-Exit: Zug vorbeigefahren ───────────────────────
        if self.platform:
            if self.platform._dead or (self.platform.z - self.platform.hz) < -0.5:
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
                self.y          = self._base_y
                self.vel_y      = 0.0
                self.is_jumping = False
                self.platform   = None
                self._ramp_jump = False

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

        # ── Rampen-Neigung (rotation_x) ───────────────────────────────
        # Beim Hochlaufen auf der Rampe neigt sich der Körper vorwärts,
        # beim Fallen wieder zurück auf 0.
        if self._ramp_jump and self.is_jumping:
            target_rx = 28 if self.vel_y > 1.0 else 0
            self.rotation_x = lerp(self.rotation_x, target_rx, min(10 * dt, 1))
        elif self.rotation_x != 0:
            self.rotation_x = lerp(self.rotation_x, 0, min(12 * dt, 1))
            if abs(self.rotation_x) < 0.3:
                self.rotation_x = 0

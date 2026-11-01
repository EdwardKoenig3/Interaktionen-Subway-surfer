import random
from ursina import Entity, destroy, color as ursina_color
from constants import (
    LANES, LANE_COUNT, SPAWN_Z, DESPAWN_Z,
    C_COIN, C_CAR, C_CABIN,
    CAR_SX, CAR_SY, CAR_Y, CAR_CAB_TOP,
    TRAIN_SX, TRAIN_SY, TRAIN_Y,
    OVERHEAD_Y, OVERHEAD_SY,
    PLAYER_HW, PLAYER_HH,
)
from game_state import GS


# ── Hindernisdefinitionen ─────────────────────────────────────────────
OBS_DEFS = {
    'car':      {'sx': CAR_SX,   'sy': CAR_SY,   'sz': 3.8,  'y': CAR_Y,   'tex': None},
    'train':    {'sx': TRAIN_SX, 'sy': TRAIN_SY,  'sz': None, 'y': TRAIN_Y, 'tex': 'textures/train.png'},
    'overhead': {'sx': 3.0,      'sy': OVERHEAD_SY,'sz': 0.5, 'y': OVERHEAD_Y,'tex': 'textures/overhead.png'},
}

# Zuglängen (Einheiten) pro Variante – (min, max)
TRAIN_LENGTHS = {
    'train':      (5.0, 10.0),
    'train_long': (12.0, 20.0),
    'train_xl':   (22.0, 32.0),
}


class Obstacle(Entity):
    """
    Generisches Hindernis: Auto (springbare Plattform), Zug (Wand – nur Spurwechsel),
    Deckenbalken (nur Slide). Zuglängen-Varianten: 'train', 'train_long', 'train_xl'.
    """

    def __init__(self, lane: int, kind: str):
        base_kind = 'train' if kind.startswith('train') else kind
        d  = OBS_DEFS[base_kind]

        if base_kind == 'train':
            lo, hi = TRAIN_LENGTHS.get(kind, (5.0, 10.0))
            sz = random.uniform(lo, hi)
        else:
            sz = d['sz']

        # Vorderkante liegt bei SPAWN_Z (nicht die Mitte) – sonst tauchen lange
        # Züge deutlich näher auf als kurze Hindernisse.
        cz = SPAWN_Z + sz * 0.5

        # Entity aufbauen — Auto = unsichtbarer Träger (texturierte Quads als _deco),
        # Train/Overhead = Würfel mit Wandtextur.
        if base_kind == 'car':
            super().__init__(
                model=None,
                scale=(d['sx'], d['sy'], sz),
                position=(LANES[lane], d['y'], cz),
            )
        else:
            super().__init__(
                model='cube', texture=d['tex'],
                texture_scale=(sz / 2, 1) if base_kind == 'train' else (1, 1),
                scale=(d['sx'], d['sy'], sz),
                position=(LANES[lane], d['y'], cz),
            )

        self.lane         = lane
        self.prev_z       = cz               # z im letzten Frame (für z_overlaps)
        self.kind         = base_kind
        self.hw           = d['sx'] * 0.46   # halbe Breite (Kollision)
        self.hh           = d['sy'] * 0.48   # halbe Höhe   (Kollision)
        self.hz           = sz * 0.5          # halbe Tiefe  (Kollision)
        if base_kind == 'car':
            # Kollision deckt die Fahrerkabine mit ab → solide, kein Durchlaufen,
            # und das Dach (CAR_CAB_TOP) wird zur Landefläche.
            self.hh       = (CAR_CAB_TOP - CAR_Y)
        self._dead        = False
        self.has_platform = base_kind in ('train', 'car')
        self._deco: list[Entity] = []

        if base_kind == 'train':
            self._build_train(lane, sz, cz)
        elif base_kind == 'overhead':
            self._build_overhead(lane, cz)
        elif base_kind == 'car':
            self._build_car(lane, sz, cz)

    # ── Visuelle Dekoration ──────────────────────────────────────────

    def _build_train(self, lane: int, sz: float, cz: float):
        front_z = cz - sz * 0.5
        front = Entity(model='cube', texture='textures/train_front.png',
                       scale=(TRAIN_SX, TRAIN_SY, 0.18),
                       position=(LANES[lane], TRAIN_Y, front_z - 0.09))
        self._deco.append(front)

        num_w = max(2, int(sz / 2.2))
        for fi in range(num_w):
            t  = fi / max(num_w - 1, 1)
            fz = cz - sz * 0.42 + t * sz * 0.84
            for side in [-0.6, 0.6]:
                w = Entity(model='cube', texture='textures/train_window.png',
                           scale=(0.45, 0.4, 0.5),
                           position=(LANES[lane] + side, TRAIN_Y + 0.3, fz))
                self._deco.append(w)

    def _build_car(self, lane: int, sz: float, car_z: float):
        # Atlas-Layout (3×2, identisch zum Spieler):
        #   obere Reihe:  [f (-Z)] [b (+Z)] [r (+X)]
        #   untere Reihe: [l (-X)] [t (+Y)] [bot (-Y)]
        UV = {
            'f':   (0,    0.5),
            'b':   (1/3,  0.5),
            'r':   (2/3,  0.5),
            'l':   (0,    0),
            't':   (1/3,  0),
            'bot': (2/3,  0),
        }
        def _add_box(cx, cy, cz, W, H, D, atlas):
            """Texturierter Quader aus 6 Quads – nutzt den 3×2-Atlas pro Seite."""
            hw, hh, hd = W/2, H/2, D/2
            for key, (ox, oy, oz), rot, sw, sh in (
                ('f',   ( 0,   0,  -hd), (  0,   0, 0), W, H),
                ('b',   ( 0,   0,   hd), (  0, 180, 0), W, H),
                ('l',   (-hw,  0,    0), (  0,  90, 0), D, H),
                ('r',   ( hw,  0,    0), (  0, -90, 0), D, H),
                ('t',   ( 0,  hh,    0), (-90,   0, 0), W, D),
                ('bot', ( 0, -hh,    0), ( 90,   0, 0), W, D),
            ):
                u, v = UV[key]
                self._deco.append(Entity(
                    model='quad', double_sided=True,
                    texture=atlas,
                    texture_scale=(1/3, 0.5),
                    texture_offset=(u, v),
                    position=(cx + ox, cy + oy, cz + oz),
                    rotation=rot, scale=(sw, sh, 1),
                ))

        cx, cy, cz = LANES[lane], CAR_Y, car_z
        # Karosserie (unten)
        _add_box(cx, cy, cz, CAR_SX, CAR_SY, sz, 'textures/07_car.png')
        # Kabine (oben): schmaler, kürzer, niedrig gehalten, Oberkante = CAR_CAB_TOP.
        # So bleibt das Auto überspringbar und die Kabine deckt sich mit der Kollision.
        cab_W = CAR_SX * 0.78
        cab_H = 0.50
        cab_D = sz * 0.55
        cab_y = CAR_CAB_TOP - cab_H * 0.5
        _add_box(cx, cab_y, cz, cab_W, cab_H, cab_D, 'textures/07b_car_cabin.png')

    def _build_overhead(self, lane: int, cz: float):
        for side in [-1.3, 1.3]:
            pillar = Entity(model='cube', texture='textures/overhead.png',
                            scale=(0.22, OVERHEAD_Y * 0.9, 0.4),
                            position=(LANES[lane] + side, OVERHEAD_Y * 0.45, cz))
            self._deco.append(pillar)

    # ── Update & Kollision ───────────────────────────────────────────

    def update(self):
        if self._dead:
            return
        # Position vor der Bewegung merken → z_overlaps() prüft die ganze in
        # diesem Frame zurückgelegte Strecke (bei Tempo 240 ≈ 4 Einheiten/Frame)
        self.prev_z = self.z
        if not GS.running or GS.paused:
            return
        delta = GS.speed * __import__('ursina').time.dt
        self.z -= delta
        for d in self._deco:
            d.z -= delta
        # Erst entfernen, wenn auch die HINTERKANTE vorbei ist – sonst verschwand
        # ein langer Zug, während der Spieler noch auf seinem Dach stand
        if self.z + self.hz < DESPAWN_Z:
            self._destroy()

    def _destroy(self):
        self._dead = True
        for d in self._deco:
            destroy(d)
        destroy(self)

    def z_overlaps(self, player_z: float, margin: float) -> bool:
        """Überschneidet sich das Hindernis in z mit dem Spieler – inklusive der
        Strecke seit dem letzten Frame? Ohne diesen "Sweep" springen schmale
        Hindernisse (Deckenbalken: 0.5 tief) bei hohem Tempo einfach über den
        Spieler hinweg, ohne dass je eine Überschneidung gemessen wird."""
        lo = min(self.z, self.prev_z) - self.hz - margin
        hi = max(self.z, self.prev_z) + self.hz + margin
        return lo < player_z < hi

    def hits_body(self, player) -> bool:
        phw, phh = player.half_extents()
        if not self.z_overlaps(player.z, 0.4):
            return False
        if abs(self.x - player.x) >= self.hw + phw - 0.05:
            return False
        return abs(self.y - player.y) < self.hh + phh - 0.1

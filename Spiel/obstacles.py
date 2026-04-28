import random
from ursina import Entity, destroy, color as ursina_color
from constants import (
    LANES, LANE_COUNT, SPAWN_Z, DESPAWN_Z,
    C_COIN, C_CAR, C_CABIN,
    CAR_SX, CAR_SY, CAR_Y,
    TRAIN_SX, TRAIN_SY, TRAIN_Y, TRAIN_TOP, RAMP_LEN,
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

# Zuglängen (Einheiten) pro Variante
_TRAIN_LENGTHS = {
    'train':      (5.0, 10.0),
    'train_long': (12.0, 20.0),
    'train_xl':   (22.0, 32.0),
}


class Obstacle(Entity):
    """
    Generisches Hindernis: Auto (springbare Plattform), Zug (Rampen-Plattform),
    Deckenbalken (nur Slide). Zuglängen-Varianten: 'train', 'train_long', 'train_xl'.
    """

    def __init__(self, lane: int, kind: str):
        base_kind = 'train' if kind.startswith('train') else kind
        d  = OBS_DEFS[base_kind]

        if base_kind == 'train':
            lo, hi = _TRAIN_LENGTHS.get(kind, (5.0, 10.0))
            sz = random.uniform(lo, hi)
        else:
            sz = d['sz']

        # Entity aufbauen — Auto bekommt Vollfarbe, Rest Textur
        if base_kind == 'car':
            super().__init__(
                model='cube', color=C_CAR,
                scale=(d['sx'], d['sy'], sz),
                position=(LANES[lane], d['y'], SPAWN_Z),
            )
        else:
            super().__init__(
                model='cube', texture=d['tex'],
                texture_scale=(sz / 2, 1) if base_kind == 'train' else (1, 1),
                scale=(d['sx'], d['sy'], sz),
                position=(LANES[lane], d['y'], SPAWN_Z),
            )

        self.kind         = base_kind
        self.hw           = d['sx'] * 0.46   # halbe Breite (Kollision)
        self.hh           = d['sy'] * 0.48   # halbe Höhe   (Kollision)
        self.hz           = sz * 0.5          # halbe Tiefe  (Kollision)
        self._dead        = False
        self.has_ramp     = False
        self.has_platform = base_kind in ('train', 'car')
        self._deco: list[Entity] = []

        if base_kind == 'train':
            self._build_train(lane, sz)
        elif base_kind == 'overhead':
            self._build_overhead(lane)
        elif base_kind == 'car':
            self._build_car(lane, sz)

    # ── Visuelle Dekoration ──────────────────────────────────────────

    def _build_train(self, lane: int, sz: float):
        self.has_ramp = random.random() < 0.45

        front_z = SPAWN_Z - sz * 0.5
        front = Entity(model='cube', texture='textures/train_front.png',
                       scale=(TRAIN_SX, TRAIN_SY, 0.18),
                       position=(LANES[lane], TRAIN_Y, front_z - 0.09))
        self._deco.append(front)

        num_w = max(2, int(sz / 2.2))
        for fi in range(num_w):
            t  = fi / max(num_w - 1, 1)
            fz = SPAWN_Z - sz * 0.42 + t * sz * 0.84
            for side in [-0.6, 0.6]:
                w = Entity(model='cube', texture='textures/train_window.png',
                           scale=(0.45, 0.4, 0.5),
                           position=(LANES[lane] + side, TRAIN_Y + 0.3, fz))
                self._deco.append(w)

        if self.has_ramp:
            front_z = SPAWN_Z - sz * 0.5
            for seg in range(5):
                t      = seg / 4.0
                seg_z  = front_z - RAMP_LEN * (1.0 - t * 0.5)
                seg_y  = TRAIN_Y * 0.05 + t * (TRAIN_TOP - TRAIN_Y * 0.05)
                seg_sy = 0.12 + t * 0.08
                ramp_seg = Entity(model='cube', texture='textures/ramp.png',
                                  scale=(TRAIN_SX * 0.9, seg_sy, RAMP_LEN / 6),
                                  position=(LANES[lane], seg_y, seg_z))
                self._deco.append(ramp_seg)
            face = Entity(model='cube', texture='textures/ramp.png',
                          scale=(TRAIN_SX, TRAIN_SY, 0.15),
                          position=(LANES[lane], TRAIN_Y, front_z - 0.07))
            self._deco.append(face)

    def _build_car(self, lane: int, sz: float):
        car_top_y = CAR_Y + CAR_SY * 0.5

        # Kabine (oberer Aufbau)
        cabin = Entity(model='cube', color=C_CABIN,
                       scale=(CAR_SX * 0.75, CAR_SY * 0.45, sz * 0.52),
                       position=(LANES[lane], car_top_y + CAR_SY * 0.22, SPAWN_Z))
        self._deco.append(cabin)

        # Scheinwerfer vorne
        for side in (-0.55, 0.55):
            hl = Entity(model='cube', color=ursina_color.rgb(240, 230, 160),
                        scale=(0.28, 0.14, 0.06),
                        position=(LANES[lane] + side, car_top_y - CAR_SY * 0.18,
                                  SPAWN_Z - sz * 0.5 - 0.03))
            self._deco.append(hl)

        # Rücklichter hinten
        for side in (-0.55, 0.55):
            rl = Entity(model='cube', color=ursina_color.rgb(220, 40, 40),
                        scale=(0.28, 0.14, 0.06),
                        position=(LANES[lane] + side, car_top_y - CAR_SY * 0.18,
                                  SPAWN_Z + sz * 0.5 + 0.03))
            self._deco.append(rl)

    def _build_overhead(self, lane: int):
        for side in [-1.3, 1.3]:
            pillar = Entity(model='cube', texture='textures/overhead.png',
                            scale=(0.22, OVERHEAD_Y * 0.9, 0.4),
                            position=(LANES[lane] + side, OVERHEAD_Y * 0.45, SPAWN_Z))
            self._deco.append(pillar)

    # ── Update & Kollision ───────────────────────────────────────────

    def update(self):
        if not GS.running or self._dead:
            return
        delta = GS.speed * __import__('ursina').time.dt
        self.z -= delta
        for d in self._deco:
            d.z -= delta
        if self.z < DESPAWN_Z:
            self._destroy()

    def _destroy(self):
        self._dead = True
        for d in self._deco:
            destroy(d)
        destroy(self)

    def hits_body(self, player) -> bool:
        phw, phh = player.half_extents()
        if abs(self.z - player.z) >= self.hz + 0.4:
            return False
        if abs(self.x - player.x) >= self.hw + phw - 0.05:
            return False
        return abs(self.y - player.y) < self.hh + phh - 0.1

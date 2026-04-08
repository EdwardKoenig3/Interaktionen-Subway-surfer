import random
from ursina import Entity, destroy
from constants import (
    LANES, LANE_COUNT, SPAWN_Z, DESPAWN_Z,
    C_BARRIER, C_TRAIN, C_OVERHEAD, C_TUNNEL, C_RAMP,
    C_WIN_YEL, C_WIN_RED, C_COIN,
    TRAIN_SX, TRAIN_SY, TRAIN_Y, TRAIN_TOP, RAMP_LEN,
    OVERHEAD_Y, OVERHEAD_SY,
    PLAYER_HW, PLAYER_HH,
)
from game_state import GS


# ── Hindernisdefinitionen ─────────────────────────────────────────────
OBS_DEFS = {
    'barrier':  {'sx': 2.0, 'sy': 0.55,      'sz': 0.45, 'y': 0.275,    'col': C_BARRIER},
    'train':    {'sx': TRAIN_SX, 'sy': TRAIN_SY, 'sz': 8.0, 'y': TRAIN_Y, 'col': C_TRAIN},
    'overhead': {'sx': 3.0, 'sy': OVERHEAD_SY,'sz': 0.5,  'y': OVERHEAD_Y,'col': C_OVERHEAD},
}


class Obstacle(Entity):
    """
    Generisches Hindernis (Barriere, Zug, Deckenbalken).
    Züge bekommen zufällige Länge; 45% haben eine Rampe an der Vorderkante.
    """

    def __init__(self, lane: int, kind: str):
        d  = OBS_DEFS[kind]
        sz = (random.uniform(5.0, 12.0) if kind == 'train' else d['sz'])

        super().__init__(
            model='cube', color=d['col'],
            scale=(d['sx'], d['sy'], sz),
            position=(LANES[lane], d['y'], SPAWN_Z),
        )
        self.kind     = kind
        self.hw       = d['sx'] * 0.46   # halbe Breite (Kollision)
        self.hh       = d['sy'] * 0.48   # halbe Höhe   (Kollision)
        self.hz       = sz * 0.5         # halbe Tiefe   (Kollision)
        self._dead    = False
        self.has_ramp = False
        self._deco: list[Entity] = []

        if kind == 'train':
            self._build_train(lane, sz)
        elif kind == 'overhead':
            self._build_overhead(lane)
        elif kind == 'barrier':
            Entity(parent=self, model='cube', color=C_COIN,
                   scale=(1.0, 0.07, 1.05), position=(0, 0.3, 0))

    # ── Visuelle Dekoration ──────────────────────────────────────────

    def _build_train(self, lane: int, sz: float):
        self.has_ramp = random.random() < 0.45

        # Roter Längsstreifen (absolut, kein parent)
        stripe = Entity(model='cube', color=C_WIN_RED,
                        scale=(TRAIN_SX, 0.18, sz),
                        position=(LANES[lane], TRAIN_Y - TRAIN_SY * 0.42, SPAWN_Z))
        self._deco.append(stripe)

        # Fenster gleichmäßig über die Länge verteilt
        num_w = max(2, int(sz / 2.2))
        for fi in range(num_w):
            t  = fi / max(num_w - 1, 1)
            fz = SPAWN_Z - sz * 0.42 + t * sz * 0.84
            for side in [-0.6, 0.6]:
                w = Entity(model='cube', color=C_WIN_YEL,
                           scale=(0.45, 0.4, 0.5),
                           position=(LANES[lane] + side, TRAIN_Y + 0.3, fz))
                self._deco.append(w)

        if self.has_ramp:
            # Rampe: flacher Streifen VOR dem Zug auf Bodenhöhe (kein Durchdringen)
            front_z = SPAWN_Z - sz * 0.5          # Vorderkante des Zugs
            # Schräger Anfahrtsstreifen – liegt komplett VOR dem Zug
            for seg in range(5):
                t      = seg / 4.0
                seg_z  = front_z - RAMP_LEN * (1.0 - t * 0.5)   # vor Zug
                seg_y  = TRAIN_Y * 0.05 + t * (TRAIN_TOP - TRAIN_Y * 0.05)
                seg_sy = 0.12 + t * 0.08
                ramp_seg = Entity(model='cube', color=C_RAMP,
                                  scale=(TRAIN_SX * 0.9, seg_sy, RAMP_LEN / 6),
                                  position=(LANES[lane], seg_y, seg_z))
                self._deco.append(ramp_seg)
            # Farbige Vorderfront des Zuges als Ramp-Markierung
            face = Entity(model='cube', color=C_RAMP,
                          scale=(TRAIN_SX, TRAIN_SY, 0.15),
                          position=(LANES[lane], TRAIN_Y, front_z - 0.07))
            self._deco.append(face)

    def _build_overhead(self, lane: int):
        for side in [-1.3, 1.3]:
            pillar = Entity(model='cube', color=C_OVERHEAD,
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
        """
        True wenn Spieler den Hinderniskörper berührt.
        Nutzt player.z (kann durch Pushback negativ sein).
        """
        phw, phh = player.half_extents()
        if abs(self.z - player.z) >= self.hz + 0.4:
            return False
        if abs(self.x - player.x) >= self.hw + phw - 0.05:
            return False
        return abs(self.y - player.y) < self.hh + phh - 0.1


class TunnelObstacle:
    """
    Kein Entity selbst – verwaltet mehrere Wand-Entities.
    Blockiert 2 von 3 Spuren, lässt eine offen.
    """

    def __init__(self):
        self.open_lane = random.randint(0, LANE_COUNT - 1)
        self._walls: list[Entity] = []
        self._dead = False
        self.z     = float(SPAWN_Z)
        self.hz    = 1.5

        for li in range(LANE_COUNT):
            if li == self.open_lane:
                continue
            w = Entity(model='cube', color=C_TUNNEL,
                       scale=(2.8, 3.5, 3.0),
                       position=(LANES[li], 1.75, SPAWN_Z))
            self._walls.append(w)

        top = Entity(model='cube', color=C_TUNNEL,
                     scale=(9.0, 0.4, 3.0),
                     position=(0, 3.7, SPAWN_Z))
        self._walls.append(top)

    def update(self):
        if not GS.running or self._dead:
            return
        delta = GS.speed * __import__('ursina').time.dt
        self.z -= delta
        for w in self._walls:
            w.z -= delta
        if self.z < DESPAWN_Z:
            self._dead = True
            for w in self._walls:
                destroy(w)

    def hits_body(self, player) -> bool:
        phw, phh = player.half_extents()
        if abs(self.z - player.z) >= self.hz + 0.4:
            return False
        for li in range(LANE_COUNT):
            if li == self.open_lane:
                continue
            if abs(LANES[li] - player.x) < 1.4 + phw - 0.1:
                if abs(1.75 - player.y) < 1.68 + phh - 0.1:
                    return True
        return False

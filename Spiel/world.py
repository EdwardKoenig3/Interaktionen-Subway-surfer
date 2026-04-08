import random
from ursina import Entity
from constants import (
    C_GROUND, C_LANEMARK, C_BLDG, C_WIN_YEL,
    TILE_LEN, TILE_COUNT, DESPAWN_Z,
)
from game_state import GS


class GroundTile(Entity):
    """Scrollende Bodenkachel – wird recycelt wenn sie hinter dem Spieler verschwindet."""

    def __init__(self, z: float):
        super().__init__(
            model='cube', color=C_GROUND,
            scale=(9, 0.3, TILE_LEN),
            position=(0, -0.15, z),
        )
        # Spurmarkierungen als Child-Entities
        for lx in [-1.39, 1.39]:
            Entity(
                parent=self, model='cube', color=C_LANEMARK,
                scale=(0.03 / 9, 1.1, 0.35 / TILE_LEN),
                position=(lx / 4.5, 0.52, 0),
            )

    def update(self):
        if not GS.running:
            return
        self.z -= GS.speed * __import__('ursina').time.dt
        if self.z < DESPAWN_Z:
            self.z += TILE_COUNT * TILE_LEN


def make_buildings():
    """Erstellt statische Hintergrundgebäude auf beiden Seiten."""
    for side in [-1, 1]:
        for i in range(8):
            h = 4 + (i * 47 + 11) % 9
            b = Entity(
                model='cube', color=random.choice(C_BLDG),
                scale=(2.2, h, TILE_LEN - 0.3),
                position=(side * 7.5, h / 2 - 0.15, i * TILE_LEN - 10),
                eternal=True,
            )
            for wy in range(3):
                for wz in range(3):
                    Entity(
                        parent=b, model='cube', color=C_WIN_YEL,
                        scale=(0.5 / 2.2, 0.25 / h, 0.4 / (TILE_LEN - 0.3)),
                        position=(side * 0.52, -0.25 + wy * 0.25, -0.25 + wz * 0.25),
                    )

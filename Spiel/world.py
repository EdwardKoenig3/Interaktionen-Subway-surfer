import random
from ursina import Entity
from constants import (
    C_GROUND, C_LANEMARK, C_BLDG, C_WIN_YEL,
    TILE_LEN, TILE_COUNT, DESPAWN_Z,
)
from game_state import GS


class GroundTile(Entity):
    """Scrollende Straßenkachel – wird recycelt wenn sie hinter dem Spieler verschwindet."""

    def __init__(self, z: float):
        super().__init__(
            model='cube', texture='textures/08_road.png',
            texture_scale=(2, 2),
            scale=(9, 0.3, TILE_LEN),
            position=(0, -0.15, z),
        )
        # Spurmarkierungen als Child-Entities
        for lx in [-1.39, 1.39]:
            Entity(
                parent=self, model='cube', texture='textures/lanemark.png',
                scale=(0.03 / 9, 1.1, 0.35 / TILE_LEN),
                position=(lx / 4.5, 0.52, 0),
            )

    def update(self):
        if not GS.running:
            return
        self.z -= GS.speed * __import__('ursina').time.dt
        if self.z < DESPAWN_Z:
            self.z += TILE_COUNT * TILE_LEN


class SidewalkTile(Entity):
    """Bürgersteig-Kachel zwischen Straße und Gebäuden, scrollt wie der Boden."""

    def __init__(self, z: float, side: int):
        super().__init__(
            model='cube', texture='textures/09_sidewalk.png',
            texture_scale=(1, 6),
            scale=(1.9, 0.4, TILE_LEN),
            position=(side * 5.45, -0.10, z),
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
            Entity(
                model='cube', texture='textures/building.png',
                texture_scale=(1, h / 4),
                scale=(2.2, h, TILE_LEN - 0.3),
                position=(side * 7.5, h / 2 - 0.15, i * TILE_LEN - 10),
                eternal=True,
            )

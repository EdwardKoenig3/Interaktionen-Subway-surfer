from ursina import Entity
from constants import C_COIN, LANES, DESPAWN_Z, PLAYER_HW
from game_state import GS


class Coin(Entity):
    """
    Statische Münze (keine Rotation/Bob-Animation).
    Kann auf verschiedenen Höhen spawnen (Boden, Sprungbogen, Zugdach).
    Wird nur eingesammelt wenn Spieler auf gleicher Höhe ist.
    """

    def __init__(self, lane: int, z: float, y: float = 1.0):
        super().__init__(
            model='sphere', color=C_COIN,
            scale=0.35,
            position=(LANES[lane], y, z),
        )
        self._dead = False

    def update(self):
        if not GS.running or self._dead:
            return
        self.z -= GS.speed * __import__('ursina').time.dt
        if self.z < DESPAWN_Z:
            self._dead = True
            __import__('ursina').destroy(self)

    def collect(self, player) -> bool:
        """True wenn Spieler nah genug ist UND auf gleicher Höhe."""
        return (
            not self._dead
            and abs(self.x - player.x) < 0.60
            and abs(self.z - player.z) < 0.60
            and abs(self.y - player.y) < 0.85
        )

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
            model='sphere', texture='textures/coin.png',
            scale=0.35,
            position=(LANES[lane], y, z),
        )
        self._dead = False
        self.prev_z = z   # z im letzten Frame (für die Sweep-Prüfung in collect)

    def update(self):
        if self._dead:
            return
        self.prev_z = self.z
        if not GS.running or GS.paused:
            return
        self.z -= GS.speed * __import__('ursina').time.dt
        if self.z < DESPAWN_Z:
            self._dead = True
            __import__('ursina').destroy(self)

    def collect(self, player) -> bool:
        """True wenn Spieler nah genug ist UND auf gleicher Höhe.

        In z wird die ganze seit dem letzten Frame zurückgelegte Strecke geprüft –
        bei hohem Tempo würde die Münze sonst zwischen zwei Frames durchrutschen.
        """
        if self._dead:
            return False
        lo = min(self.z, self.prev_z) - 0.60
        hi = max(self.z, self.prev_z) + 0.60
        return (
            lo < player.z < hi
            and abs(self.x - player.x) < 0.60
            and abs(self.y - player.y) < 0.85
        )

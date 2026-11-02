from constants import INITIAL_SPD, MAX_LIVES
from powerups import PowerState


class GS:
    """Geteilter Track-Zustand (beide Spieler teilen sich denselben Hindernis-Track).

    Enthält nur globale Werte: Geschwindigkeit, Zeit, Spawn-Zähler und das
    Match-Flag `running`. Spielerabhängige Werte (Punkte, Leben, Münzen,
    Game-Over) liegen pro Spieler in `PlayerState`.

    `running` bedeutet „Match aktiv" – der Track scrollt, solange mindestens ein
    Spieler lebt. Ein einzelner toter Spieler friert nur über seinen
    `PlayerState.alive` ein, der Track läuft für den anderen weiter.
    """
    speed      = INITIAL_SPD
    elapsed    = 0.0
    running    = True
    paused     = True    # startet pausiert bis Match gestartet wird
    obs_dist   = 0.0     # zurückgelegte Strecke seit dem letzten Hindernis-Spawn
    coin_timer = 0.0
    powerups   = True    # Power-ups im laufenden Match erlaubt (Menü, Taste U)

    @classmethod
    def reset(cls):
        cls.speed      = INITIAL_SPD
        cls.elapsed    = 0.0
        cls.running    = True
        cls.paused     = True
        cls.obs_dist   = 0.0
        cls.coin_timer = 0.0


class PlayerState:
    """Spielerabhängiger Zustand – eine Instanz pro Spieler (Splitscreen-Seite)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.score     = 0
        self.coins     = 0
        self.lives     = MAX_LIVES
        self.inv_timer = 0.0    # Unverwundbarkeits-Timer
        self.shake_t   = 0.0    # Kamera-Shake-Timer
        self.alive     = True   # False → Spieler hat Game-Over (Figur friert ein)
        self.powers    = PowerState()

    def is_invincible(self) -> bool:
        return self.inv_timer > 0

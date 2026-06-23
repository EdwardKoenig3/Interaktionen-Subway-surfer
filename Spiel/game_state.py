from constants import INITIAL_SPD, MAX_LIVES


class GS:
    """Geteilter Track-Zustand (beide Spieler teilen sich denselben Hindernis-Track).

    Enthält nur globale Werte: Geschwindigkeit, Zeit, Spawn-Timer und das
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
    obs_timer  = 0.0
    coin_timer = 0.0

    @classmethod
    def obs_interval(cls) -> float:
        """
        Abstände zwischen Hindernissen – großzügig für Gestensteuerung.
        Bei Startgeschwindigkeit ~2.5 s, Minimum 1.8 s.
        """
        return max(1.8, 2.8 - cls.speed * 0.03)

    @classmethod
    def reset(cls):
        cls.speed      = INITIAL_SPD
        cls.elapsed    = 0.0
        cls.running    = True
        cls.paused     = True
        cls.obs_timer  = 0.0
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

    def is_invincible(self) -> bool:
        return self.inv_timer > 0

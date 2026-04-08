from constants import INITIAL_SPD, MAX_LIVES


class GS:
    """Globaler Spielzustand – alle Felder sind Klassenvariablen."""
    speed      = INITIAL_SPD
    score      = 0
    coins      = 0
    lives      = MAX_LIVES
    elapsed    = 0.0
    running    = True
    obs_timer  = 0.0
    coin_timer = 0.0
    inv_timer  = 0.0   # Unverwundbarkeits-Timer
    shake_t    = 0.0   # Kamera-Shake-Timer

    @classmethod
    def obs_interval(cls) -> float:
        """
        Abstände zwischen Hindernissen – großzügig für Gestensteuerung.
        Bei Startgeschwindigkeit ~2.5 s, Minimum 1.8 s.
        """
        return max(1.8, 2.8 - cls.speed * 0.03)

    @classmethod
    def is_invincible(cls) -> bool:
        return cls.inv_timer > 0

    @classmethod
    def reset(cls):
        cls.speed      = INITIAL_SPD
        cls.score      = 0
        cls.coins      = 0
        cls.lives      = MAX_LIVES
        cls.elapsed    = 0.0
        cls.running    = True
        cls.obs_timer  = 0.0
        cls.coin_timer = 0.0
        cls.inv_timer  = 0.0
        cls.shake_t    = 0.0

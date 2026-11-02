"""
powerups.py – Power-ups, die der Spieler selbst auslöst.

    Kamera:   Körperhaltung kurz halten (siehe CV_Contols/poses.py)
    Tastatur: Q / E / F (Spieler links bzw. allein), J / K / L (Spieler rechts)

    shield  SCHILD   Hände vor der Brust       – fängt den nächsten Treffer ab
    glide   GLEITEN  Arme seitlich ausbreiten  – hoher, schwebender Sprung
    magnet  MAGNET   Hände in die Hüften       – zieht Münzen an

Jedes Power-up wirkt `duration` Sekunden. Danach geht es erst wieder, wenn die
Abklingzeit (`cooldown`, ab dem Auslösen gezählt) vorbei ist. Im Menü lassen
sich Power-ups abschalten (U) – dann spielt sich alles wie bisher.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerDef:
    label: str        # Anzeige im Spiel
    icon: str         # Textur (generate_textures.py)
    duration: float   # Wirkdauer in s
    cooldown: float   # Abklingzeit in s ab dem Auslösen


POWERS = {
    'shield': PowerDef('SCHILD',  'textures/pw_shield.png', 8.0, 25.0),
    'glide':  PowerDef('GLEITEN', 'textures/pw_glide.png',  2.5, 15.0),
    'magnet': PowerDef('MAGNET',  'textures/pw_magnet.png', 8.0, 20.0),
}
ORDER = ('shield', 'glide', 'magnet')   # Reihenfolge im HUD

# Gleiten: weniger Schwerkraft – steigt höher (Mitte bis ≈ 4.1, über Züge und
# Balken) und sinkt langsam. Luftzeit ≈ 2 s, passend zur Wirkdauer.
GLIDE_GRAVITY_UP   = 0.55
GLIDE_GRAVITY_DOWN = 0.30
# Magnet: Münzen bis so weit voraus fliegen zum Spieler
MAGNET_RANGE_Z = 25.0


class PowerState:
    """Wirkdauer und Abklingzeit aller Power-ups eines Spielers."""

    def __init__(self):
        self.active = {name: 0.0 for name in POWERS}     # verbleibende Wirkdauer
        self.cooldown = {name: 0.0 for name in POWERS}   # verbleibende Abklingzeit

    def is_active(self, name: str) -> bool:
        return self.active[name] > 0

    def ready(self, name: str) -> bool:
        return self.cooldown[name] <= 0

    def activate(self, name: str) -> bool:
        """Auslösen, falls nicht mehr in der Abklingzeit. True bei Erfolg."""
        if not self.ready(name):
            return False
        self.active[name] = POWERS[name].duration
        self.cooldown[name] = POWERS[name].cooldown
        return True

    def end(self, name: str) -> None:
        """Wirkung sofort beenden (z.B. Schild hat einen Treffer abgefangen)."""
        self.active[name] = 0.0

    def update(self, dt: float) -> None:
        for name in POWERS:
            self.active[name] = max(0.0, self.active[name] - dt)
            self.cooldown[name] = max(0.0, self.cooldown[name] - dt)

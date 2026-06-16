"""
menu.py – Startauswahl für Subway Surfer.

Tastatur-Navigation:
    TAB     – 1 / 2 Spieler umschalten
    1       – Steuerquelle links (bzw. Einzelspieler) durchschalten
    2       – Steuerquelle rechts durchschalten (nur 2 Spieler)
    ENTER   – Match mit aktueller Auswahl starten

Steuerquellen: TASTATUR, VISION (OSC /game/vision/*), VOICE (OSC /game/voice/*).
"""

from ursina import Entity, Text, camera, color, Color, destroy

SOURCES = ['keyboard', 'vision', 'voice']
SRC_LABEL = {'keyboard': 'TASTATUR', 'vision': 'VISION', 'voice': 'VOICE'}


class StartMenu:
    def __init__(self):
        # Konfiguration mit sinnvollen Defaults
        self.mode      = 2            # 1 oder 2 Spieler
        self.left_src  = 'vision'     # linker Spieler / Einzelspieler
        self.right_src = 'voice'      # rechter Spieler

        self.bg = Entity(parent=camera.ui, model='quad', color=Color(0, 0, 0, 0.7),
                         scale=(2, 2), z=1, eternal=True)
        self.logo = Entity(parent=camera.ui, model='quad', texture='textures/06_logo.png',
                           scale=(0.55, 0.22), position=(0, 0.33), z=0, eternal=True)
        self.title = Text('MULTIPLAYER', parent=camera.ui, origin=(0, 0),
                          position=(0, 0.16), scale=1.6, color=color.white, z=0)
        self.mode_line  = Text('', parent=camera.ui, origin=(0, 0), position=(0, 0.04),
                               scale=1.3, color=color.white, z=0)
        self.left_line  = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.06),
                               scale=1.2, color=color.white, z=0)
        self.right_line = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.14),
                               scale=1.2, color=color.white, z=0)
        self.hint = Text('TAB: Modus    1/2: Quelle    ENTER: Start',
                         parent=camera.ui, origin=(0, 0), position=(0, -0.30),
                         scale=0.9, color=Color(0.8, 0.8, 0.8, 1), z=0)
        self._elems = [self.bg, self.logo, self.title, self.mode_line,
                       self.left_line, self.right_line, self.hint]
        self.refresh()

    # ── Anzeige ──────────────────────────────────────────────────────
    def refresh(self):
        self.mode_line.text = f'Modus:  {self.mode} Spieler'
        if self.mode == 1:
            self.left_line.text  = f'Spieler:  {SRC_LABEL[self.left_src]}'
            self.right_line.text = ''
        else:
            self.left_line.text  = f'Links:  {SRC_LABEL[self.left_src]}'
            self.right_line.text = f'Rechts: {SRC_LABEL[self.right_src]}'

    def set_visible(self, visible: bool):
        for e in self._elems:
            e.enabled = visible
        if visible:
            self.refresh()

    # ── Eingabe ──────────────────────────────────────────────────────
    def handle_key(self, key) -> str | None:
        """Verarbeitet eine Taste. Gibt 'start' zurück, wenn das Match starten soll."""
        if key == 'tab':
            self.mode = 1 if self.mode == 2 else 2
            self.refresh()
        elif key == '1':
            self.left_src = self._cycle(self.left_src)
            self.refresh()
        elif key == '2' and self.mode == 2:
            self.right_src = self._cycle(self.right_src)
            self.refresh()
        elif key == 'enter':
            return 'start'
        return None

    @staticmethod
    def _cycle(src: str) -> str:
        return SOURCES[(SOURCES.index(src) + 1) % len(SOURCES)]

    def config(self) -> dict:
        if self.mode == 1:
            return {'mode': 1, 'sources': [self.left_src]}
        return {'mode': 2, 'sources': [self.left_src, self.right_src]}

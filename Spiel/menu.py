"""
menu.py – Startauswahl für Subway Surfer.

Tastatur-Navigation:
    TAB     – 1 / 2 Spieler umschalten
    1       – Steuerquelle links (bzw. Einzelspieler) durchschalten
    2       – Steuerquelle rechts durchschalten (nur 2 Spieler)
    U       – Power-ups an/aus
    ENTER   – Match mit aktueller Auswahl starten

Steuerquellen: TASTATUR, VISION (OSC /game/vision/*), VOICE (OSC /game/voice/*).
Rechts im 2-Spieler-Modus zusätzlich VISION 2 (OSC /game/vision2/*): ein zweiter
Spieler vor derselben Kamera – das Kamera-Tracking läuft dann im 2-Spieler-Modus.
Im 2-Spieler-Modus kann jede OSC-Quelle nur einem Spieler zugeordnet werden.
"""

from ursina import Entity, Text, camera, color, Color, destroy
from leaderboard import LeaderboardView

SOURCES = ['keyboard', 'vision', 'voice']
RIGHT_EXTRA = ('vision2',)  # nur für den rechten Spieler im 2-Spieler-Modus
SRC_LABEL = {'keyboard': 'TASTATUR', 'vision': 'VISION', 'voice': 'VOICE', 'vision2': 'VISION 2'}


class StartMenu:
    def __init__(self):
        # Konfiguration mit sinnvollen Defaults
        self.mode      = 1            # 1 oder 2 Spieler
        self.left_src  = 'vision'     # linker Spieler / Einzelspieler
        self.right_src = 'voice'      # rechter Spieler (wird bei 2 Spielern genutzt)
        self.powerups  = True         # Power-ups erlaubt (U)

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
        self.power_line = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.22),
                               scale=1.0, color=color.white, z=0)
        self.hint = Text('TAB: Modus    1/2: Quelle    U: Power-ups    ENTER oder beide Arme hoch: Start',
                         parent=camera.ui, origin=(0, 0), position=(0, -0.30),
                         scale=0.9, color=Color(0.8, 0.8, 0.8, 1), z=0)
        # Erinnerung, das Kamera-Tracking ebenfalls auf 2 Spieler zu stellen
        self.cam_hint = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.37),
                             scale=0.85, color=color.orange, z=0)
        self._elems = [self.bg, self.logo, self.title, self.mode_line,
                       self.left_line, self.right_line, self.power_line, self.hint, self.cam_hint]
        # Bestenliste rechts neben dem Menü (nur 1 Spieler, für die gewählte Quelle)
        self.board = LeaderboardView(x_center=0.58, y_top=0.30, width=0.40, scale=0.9)
        self._visible = True
        self.refresh()

    # ── Anzeige ──────────────────────────────────────────────────────
    def refresh(self):
        # Überschrift nur im 2-Spieler-Modus
        self.title.text = 'MULTIPLAYER' if self.mode == 2 else ''
        self.mode_line.text = f'Modus:  {self.mode} Spieler'
        if self.mode == 1:
            self.left_line.text  = f'Spieler:  {SRC_LABEL[self.left_src]}'
            self.right_line.text = ''
        else:
            self.left_line.text  = f'Links:  {SRC_LABEL[self.left_src]}'
            self.right_line.text = f'Rechts: {SRC_LABEL[self.right_src]}'
        self.power_line.text = f'Power-ups:  {"AN" if self.powerups else "AUS"}'
        self.cam_hint.text = ('Zwei Spieler vor einer Kamera: Kamera-Tracking mit --spieler 2 '
                              'starten (oder Taste M im Kamerafenster)'
                              if self.mode == 2 and self.right_src == 'vision2' else '')
        # 2-Spieler-Runden zählen nicht für die Bestenliste → dort keine Liste
        if self._visible and self.mode == 1:
            self.board.show(self.left_src)
        else:
            self.board.hide()

    def set_visible(self, visible: bool):
        self._visible = visible
        for e in self._elems:
            e.enabled = visible
        self.refresh()

    # ── Eingabe ──────────────────────────────────────────────────────
    def handle_key(self, key) -> str | None:
        """Verarbeitet eine Taste. Gibt 'start' zurück, wenn das Match starten soll."""
        if key == 'tab':
            self.mode = 1 if self.mode == 2 else 2
            # Beim Wechsel auf 2 Spieler darf rechts nicht dieselbe OSC-Quelle stehen
            if self.mode == 2 and self._conflict(self.right_src, self.left_src):
                self.right_src = self._cycle(self.right_src, self.left_src, RIGHT_EXTRA)
            self.refresh()
        elif key == '1':
            other = self.right_src if self.mode == 2 else None
            self.left_src = self._cycle(self.left_src, other)
            self.refresh()
        elif key == '2' and self.mode == 2:
            self.right_src = self._cycle(self.right_src, self.left_src, RIGHT_EXTRA)
            self.refresh()
        elif key == 'u':
            self.powerups = not self.powerups
            self.refresh()
        elif key == 'enter':
            return 'start'
        return None

    @staticmethod
    def _conflict(src: str, other: str | None) -> bool:
        """Zwei Spieler können sich keine OSC-Quelle teilen (die Queue liefert
        jeden Befehl nur einmal aus). Tastatur ist für beide möglich."""
        return src == other and src != 'keyboard'

    @classmethod
    def _cycle(cls, src: str, other: str | None = None, extra: tuple[str, ...] = ()) -> str:
        """Nächste Quelle (aus SOURCES + `extra`); überspringt die OSC-Quelle des anderen Spielers."""
        options = SOURCES + list(extra)
        nxt = options[(options.index(src) + 1) % len(options)]
        if cls._conflict(nxt, other):
            nxt = options[(options.index(nxt) + 1) % len(options)]
        return nxt

    def config(self) -> dict:
        if self.mode == 1:
            return {'mode': 1, 'sources': [self.left_src], 'powerups': self.powerups}
        return {'mode': 2, 'sources': [self.left_src, self.right_src], 'powerups': self.powerups}

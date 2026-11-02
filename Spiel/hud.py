import math

from ursina import Text, Entity, Quad, camera, color, Color, time
from constants import C_COIN, MAX_LIVES
from powerups import POWERS, ORDER

_HEART_FULL  = 'textures/05_heart_full.png'
_HEART_EMPTY = 'textures/05_heart_empty.png'
_DIM         = Color(0.35, 0.35, 0.35, 1)   # Power-up klingt noch ab
_BACKDROP    = Color(0, 0, 0, 0.5)          # dunkler Hintergrund → vor den Häusern lesbar
_NOTICE_S    = 1.2                          # so lange steht "SCHILD!" o.ä. da


class PlayerHud:
    """HUD einer Spieler-Seite (Score, Herzen, Power-ups, Game-Over).

    Münzen werden nicht separat angezeigt – sie fließen nur in den Score ein.

    `x_center` verschiebt das HUD in die jeweilige Bildschirmhälfte
    (0.0 = Vollbild/1P, negativ = linke Hälfte, positiv = rechte Hälfte).
    `x_scale` staucht die horizontale Streuung für die schmaleren Splitscreen-Hälften.
    Mit `powerups` stehen links vom Score die drei Power-ups: normal = bereit,
    größer mit gelber Zahl = wirkt noch so viele Sekunden, dunkel mit grauer
    Zahl = klingt noch so viele Sekunden ab.
    """

    def __init__(self, x_center: float = 0.0, x_scale: float = 1.0,
                 accent=None, label: str = '', powerups: bool = False):
        self.x_center = x_center
        s = x_scale
        tscale = 1.0 if x_scale >= 0.99 else 0.8   # Texte in der Hälfte etwas kleiner
        accent = accent or color.white

        self.name = Text(label, position=(x_center, 0.40), origin=(0, 0),
                         scale=1.0 * tscale, color=accent) if label else None
        self.score = Text('0', position=(x_center, 0.46), origin=(0, 0),
                          scale=2.2 * tscale, color=accent)
        self.over  = Text('', position=(x_center, 0.12), origin=(0, 0), scale=3 * tscale, color=color.red)
        self.sub   = Text('', position=(x_center, 0.00), origin=(0, 0), scale=1.5 * tscale, color=color.white)
        self.restart = Text('', position=(x_center, -0.12), origin=(0, 0), scale=1.4 * tscale, color=C_COIN)

        # In der schmalen 2-Spieler-Hälfte kleinere Symbole mit festem Abstand,
        # sonst überlappen sie sich
        size = 0.05 if x_scale >= 0.99 else 0.04
        step = 0.07 * s if x_scale >= 0.99 else 0.047

        # Herzen: jedes ist eine Liste von 1 Part (API-Kompatibilität zur alten Version)
        self.hearts = []
        for i in range(MAX_LIVES):
            cx = x_center + 0.20 * s + i * step
            cy = 0.445
            part = Entity(parent=camera.ui, model='quad', texture=_HEART_FULL,
                          color=color.white, scale=(size, size), position=(cx, cy))
            self.hearts.append([part])

        # Power-ups links vom Score (gespiegelt zu den Herzen): Symbol + Sekunden,
        # auf dunklem Hintergrund. Je Eintrag [Name, Symbol, Zahl, zuletzt gezeigter Zustand]
        self.powers = []
        self._size = size
        self.power_bg = None
        if powerups:
            x0 = x_center - 0.34 * s
            self.power_bg = Entity(parent=camera.ui, model=Quad(radius=.2), color=_BACKDROP,
                                   scale=(2 * step + size + 0.03, 0.1),
                                   position=(x0 + step, 0.428), z=0.01)
            for i, name in enumerate(ORDER):
                cx = x0 + i * step
                icon = Entity(parent=camera.ui, model='quad', texture=POWERS[name].icon,
                              color=color.white, scale=(size, size), position=(cx, 0.448))
                txt = Text('', position=(cx, 0.4), origin=(0, 0), scale=0.85 * tscale)
                self.powers.append([name, icon, txt, None])
        # Kurze Rückmeldung beim Auslösen ("SCHILD!", "SCHILD – noch 12 s")
        self.notice = Text('', position=(x_center, 0.34), origin=(0, 0), scale=1.6 * tscale)
        self.notice.enabled = False
        self._notice_left = 0.0

    def update(self, state):
        """Score/Herzen/Power-ups aus dem PlayerState übernehmen."""
        self.score.text = str(state.score)
        for i, parts in enumerate(self.hearts):
            tex = _HEART_FULL if i < state.lives else _HEART_EMPTY
            for part in parts:
                part.texture = tex
        p = state.powers
        for entry in self.powers:
            name, icon, txt, shown = entry
            if p.is_active(name):
                look = ('active', math.ceil(p.active[name]))
            elif not p.ready(name):
                look = ('cooldown', math.ceil(p.cooldown[name]))
            else:
                look = ('ready', 0)
            if look == shown:
                continue
            entry[3] = look
            kind, secs = look
            icon.color = _DIM if kind == 'cooldown' else color.white
            icon.scale = self._size * (1.25 if kind == 'active' else 1.0)
            txt.text   = '' if kind == 'ready' else str(secs)
            txt.color  = C_COIN if kind == 'active' else color.white
        if self._notice_left > 0:
            self._notice_left -= time.dt
            if self._notice_left <= 0:
                self.notice.enabled = False

    def notify(self, text: str, col=None):
        self.notice.text    = text
        self.notice.color   = col or color.white
        self.notice.enabled = True
        # Hintergrund passt sich der Textlänge nicht von selbst an → neu anlegen
        self.notice.create_background(radius=0.25, color=_BACKDROP)
        self._notice_left   = _NOTICE_S

    def notify_power(self, name: str, ok: bool, state):
        """Rückmeldung zu einem Auslöse-Versuch: "SCHILD!" bzw. "SCHILD – noch 12 s"."""
        if name not in POWERS:
            return
        label = POWERS[name].label
        if ok:
            self.notify(f'{label}!', C_COIN)
        elif not state.powers.ready(name):
            self.notify(f'{label} – noch {math.ceil(state.powers.cooldown[name])} s')

    def show_game_over(self, state):
        self.over.text    = 'GAME OVER'
        self.sub.text     = f'Score: {state.score}   Münzen: {state.coins}'
        self.restart.text = ''

    def clear_game_over(self):
        self.over.text = ''
        self.sub.text = ''
        self.restart.text = ''

    def destroy(self):
        from ursina import destroy
        elems = [self.score, self.over, self.sub, self.restart, self.notice]
        if self.name:
            elems.append(self.name)
        if self.power_bg:
            elems.append(self.power_bg)
        for _, icon, txt, _ in self.powers:
            elems += [icon, txt]
        for e in elems:
            destroy(e)
        for parts in self.hearts:
            for part in parts:
                destroy(part)
        self.hearts = []
        self.powers = []


def update_hearts(hearts: list, lives: int):
    """Rückwärtskompatibler Helfer (Herzen einer HUD-Seite aktualisieren)."""
    for i, parts in enumerate(hearts):
        tex = _HEART_FULL if i < lives else _HEART_EMPTY
        for part in parts:
            part.texture = tex
            part.color   = color.white

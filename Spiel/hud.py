from ursina import Text, Entity, camera, color, Color
from constants import C_COIN, MAX_LIVES

_HEART_FULL  = 'textures/05_heart_full.png'
_HEART_EMPTY = 'textures/05_heart_empty.png'


class PlayerHud:
    """HUD einer Spieler-Seite (Score, Münzen, Herzen, Game-Over).

    `x_center` verschiebt das HUD in die jeweilige Bildschirmhälfte
    (0.0 = Vollbild/1P, negativ = linke Hälfte, positiv = rechte Hälfte).
    `x_scale` staucht die horizontale Streuung für die schmaleren Splitscreen-Hälften.
    """

    def __init__(self, x_center: float = 0.0, x_scale: float = 1.0,
                 accent=None, label: str = ''):
        self.x_center = x_center
        s = x_scale
        tscale = 1.0 if x_scale >= 0.99 else 0.8   # Texte in der Hälfte etwas kleiner
        accent = accent or color.white

        self.name = Text(label, position=(x_center, 0.40), origin=(0, 0),
                         scale=1.0 * tscale, color=accent) if label else None
        self.score = Text('0', position=(x_center, 0.46), origin=(0, 0),
                          scale=2.2 * tscale, color=accent)
        self.coins = Text('$ 0', position=(x_center - 0.40 * s, 0.46), origin=(-0.5, 0),
                          scale=1.6 * tscale, color=C_COIN)
        self.over  = Text('', position=(x_center, 0.12), origin=(0, 0), scale=3 * tscale, color=color.red)
        self.sub   = Text('', position=(x_center, 0.00), origin=(0, 0), scale=1.5 * tscale, color=color.white)
        self.restart = Text('', position=(x_center, -0.12), origin=(0, 0), scale=1.4 * tscale, color=C_COIN)

        # Herzen: jedes ist eine Liste von 1 Part (API-Kompatibilität zur alten Version)
        self.hearts = []
        for i in range(MAX_LIVES):
            cx = x_center + (0.20 + i * 0.07) * s
            cy = 0.445
            part = Entity(parent=camera.ui, model='quad', texture=_HEART_FULL,
                          color=color.white, scale=(0.05, 0.05), position=(cx, cy))
            self.hearts.append([part])

    def update(self, state):
        """Score/Münzen/Herzen aus dem PlayerState übernehmen."""
        self.score.text = str(state.score)
        self.coins.text = f'$ {state.coins}'
        for i, parts in enumerate(self.hearts):
            tex = _HEART_FULL if i < state.lives else _HEART_EMPTY
            for part in parts:
                part.texture = tex

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
        elems = [self.score, self.coins, self.over, self.sub, self.restart]
        if self.name:
            elems.append(self.name)
        for e in elems:
            destroy(e)
        for parts in self.hearts:
            for part in parts:
                destroy(part)
        self.hearts = []


def update_hearts(hearts: list, lives: int):
    """Rückwärtskompatibler Helfer (Herzen einer HUD-Seite aktualisieren)."""
    for i, parts in enumerate(hearts):
        tex = _HEART_FULL if i < lives else _HEART_EMPTY
        for part in parts:
            part.texture = tex
            part.color   = color.white

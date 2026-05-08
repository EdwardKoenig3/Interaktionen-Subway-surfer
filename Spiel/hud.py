from ursina import Text, Entity, camera, color, Color
from constants import C_COIN, MAX_LIVES

_HEART_FULL  = 'textures/05_heart_full.png'
_HEART_EMPTY = 'textures/05_heart_empty.png'


def _make_heart(cx: float, cy: float, alive: bool) -> list:
    """Ein einzelnes Quad mit Herz-Textur."""
    return [
        Entity(parent=camera.ui, model='quad',
               texture=_HEART_FULL if alive else _HEART_EMPTY,
               color=color.white,
               scale=(0.06, 0.06),
               position=(cx, cy)),
    ]


def create_hud():
    score   = Text('0',   position=( 0,    0.46), origin=(0, 0),    scale=2.2, color=color.white)
    coins   = Text('$ 0', position=(-0.82, 0.46), origin=(-0.5, 0), scale=1.6, color=C_COIN)
    hint    = Text('A D   Jump (W/Space)   Slide (S)',
                   position=(0, -0.47), origin=(0, 0), scale=0.9,
                   color=Color(0.7, 0.7, 0.7, 1))
    over    = Text('', position=(0,  0.12), origin=(0, 0), scale=3,   color=color.red)
    sub     = Text('', position=(0,  0.00), origin=(0, 0), scale=1.5, color=color.white)
    restart = Text('', position=(0, -0.12), origin=(0, 0), scale=1.5, color=C_COIN)

    # Jedes "Herz" ist eine Liste von 1 Entity-Part (für API-Kompatibilität)
    hearts = []
    for i in range(MAX_LIVES):
        cx = 0.56 + i * 0.09
        cy = 0.445
        hearts.append(_make_heart(cx, cy, alive=True))

    # Pause-Overlay
    pause_bg = Entity(
        parent=camera.ui,
        model='quad',
        color=Color(0, 0, 0, 0.55),
        scale=(2, 2),
        z=1,
    )
    # Logo oben in Pause/Start
    logo = Entity(
        parent=camera.ui, model='quad',
        texture='textures/06_logo.png',
        scale=(0.55, 0.22),
        position=(0, 0.28),
        z=0,
    )
    logo.enabled = False
    pause_title = Text('',  position=(0, -0.02), origin=(0, 0), scale=2.4, color=color.white, z=0)
    pause_sub   = Text('',  position=(0, -0.14), origin=(0, 0), scale=1.4,
                        color=Color(0.85, 0.85, 0.85, 1), z=0)

    return score, coins, hint, over, sub, restart, hearts, pause_bg, pause_title, pause_sub, logo


def update_hearts(hearts: list, lives: int):
    for i, parts in enumerate(hearts):
        tex = _HEART_FULL if i < lives else _HEART_EMPTY
        for part in parts:
            part.texture = tex
            part.color   = color.white

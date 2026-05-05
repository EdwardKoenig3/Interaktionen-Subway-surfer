from ursina import Text, Entity, camera, color, Color
from constants import C_COIN, MAX_LIVES

_HEART_RED  = color.red
_HEART_DEAD = Color(0.25, 0.10, 0.10, 1)


def _make_heart(cx: float, cy: float, alive: bool) -> list:
    """Drei überlappende Quads, die eine Herz-Silhouette ergeben."""
    c = _HEART_RED if alive else _HEART_DEAD
    parts = [
        Entity(parent=camera.ui, model='quad', color=c,
               scale=(0.052, 0.052), rotation_z=45,
               position=(cx, cy - 0.006)),
        Entity(parent=camera.ui, model='quad', color=c,
               scale=(0.036, 0.036), position=(cx - 0.017, cy + 0.013)),
        Entity(parent=camera.ui, model='quad', color=c,
               scale=(0.036, 0.036), position=(cx + 0.017, cy + 0.013)),
    ]
    return parts


def create_hud():
    score   = Text('0',   position=( 0,    0.46), origin=(0, 0),    scale=2.2, color=color.white)
    coins   = Text('$ 0', position=(-0.82, 0.46), origin=(-0.5, 0), scale=1.6, color=C_COIN)
    hint    = Text('A D   Jump (W/Space)   Slide (S)',
                   position=(0, -0.47), origin=(0, 0), scale=0.9,
                   color=Color(0.7, 0.7, 0.7, 1))
    over    = Text('', position=(0,  0.12), origin=(0, 0), scale=3,   color=color.red)
    sub     = Text('', position=(0,  0.00), origin=(0, 0), scale=1.5, color=color.white)
    restart = Text('', position=(0, -0.12), origin=(0, 0), scale=1.5, color=C_COIN)

    # Jedes "Herz" ist eine Liste von 3 Entity-Parts
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
    pause_title = Text('',  position=(0,  0.08), origin=(0, 0), scale=3.5, color=color.white, z=0)
    pause_sub   = Text('',  position=(0, -0.06), origin=(0, 0), scale=1.4,
                        color=Color(0.8, 0.8, 0.8, 1), z=0)

    return score, coins, hint, over, sub, restart, hearts, pause_bg, pause_title, pause_sub


def update_hearts(hearts: list, lives: int):
    for i, parts in enumerate(hearts):
        c = _HEART_RED if i < lives else _HEART_DEAD
        for part in parts:
            part.color = c

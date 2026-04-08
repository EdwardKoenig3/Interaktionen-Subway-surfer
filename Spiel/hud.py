from ursina import Text, Entity, camera, color, Color
from constants import C_COIN, MAX_LIVES

_HEART_FONT = 'C:/Windows/Fonts/arialuni.ttf'   # Arial Unicode – hat ♥


def create_hud():
    """
    Erstellt alle HUD-Elemente. Muss NACH Ursina-App-Init aufgerufen werden.
    Gibt (score, coins, hint, over, sub, restart, hearts) zurück.
    """
    score   = Text('0',   position=( 0,    0.46), origin=(0, 0),    scale=2.2, color=color.white)
    coins   = Text('$ 0', position=(-0.82, 0.46), origin=(-0.5, 0), scale=1.6, color=C_COIN)
    hint    = Text('A D   Jump (W/Space)   Slide (S)',
                   position=(0, -0.47), origin=(0, 0), scale=0.9,
                   color=Color(0.7, 0.7, 0.7, 1))
    over    = Text('', position=(0,  0.12), origin=(0, 0), scale=3,   color=color.red)
    sub     = Text('', position=(0,  0.00), origin=(0, 0), scale=1.5, color=color.white)
    restart = Text('', position=(0, -0.12), origin=(0, 0), scale=1.5, color=C_COIN)

    # Herzen: ♥-Symbol mit Arial Unicode, Fallback auf rote Rauten
    hearts = []
    for i in range(MAX_LIVES):
        try:
            h = Text(
                text='\u2665',          # ♥
                font=_HEART_FONT,
                position=(0.56 + i * 0.075, 0.445),
                origin=(0, 0),
                scale=2.8,
                color=color.red,
            )
        except Exception:
            # Fallback: rote Raute (quad rotiert 45°)
            h = Entity(
                parent=camera.ui,
                model='quad',
                color=color.red,
                scale=(0.048, 0.048),
                rotation_z=45,
                position=(0.56 + i * 0.075, 0.445),
            )
        hearts.append(h)

    return score, coins, hint, over, sub, restart, hearts


def update_hearts(hearts: list, lives: int):
    """Aktualisiert die Herzanzeige oben rechts."""
    for i, h in enumerate(hearts):
        h.color = color.red if i < lives else Color(0.25, 0.10, 0.10, 1)

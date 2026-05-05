"""
generate_textures.py  –  Pixel-Art Texturen (16×16 Kacheln, Minecraft-Stil)
Einmal ausführen: python generate_textures.py
"""
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), 'textures')
os.makedirs(OUT, exist_ok=True)


def save(img: Image.Image, name: str):
    img.save(os.path.join(OUT, name))
    print(f'  {name}')


def canvas(w: int, h: int, col: tuple) -> tuple[Image.Image, ImageDraw.Draw]:
    i = Image.new('RGBA', (w, h), (*col[:3], 255))
    return i, ImageDraw.Draw(i)


def px(draw: ImageDraw.Draw, x: int, y: int, col: tuple):
    draw.point((x, y), fill=(*col[:3], col[3] if len(col) == 4 else 255))


def row(draw: ImageDraw.Draw, y: int, w: int, col: tuple):
    draw.line([(0, y), (w - 1, y)], fill=(*col[:3], 255))


def block(draw: ImageDraw.Draw, x0: int, y0: int, x1: int, y1: int, col: tuple):
    draw.rectangle([x0, y0, x1, y1], fill=(*col[:3], 255))


# ── Farb-Palette ─────────────────────────────────────────────────────
ASP     = (44,  44,  44)   # Asphalt
ASP_L   = (62,  62,  62)   # Asphalt hell
ASP_D   = (28,  28,  28)   # Asphalt dunkel
MARK    = (220, 220, 210)   # Spurmarkierung

BUS     = (196, 26,  26)   # Bus rot
BUS_D   = (124, 12,  12)   # Bus dunkelrot (Schatten)
BUS_L   = (228, 56,  56)   # Bus hellrot (Licht)
BUS_YEL = (240, 220, 36)   # Bus Zierstreifen
BUS_WIN = (160, 200, 230)   # Bus Fenster (blau-grau)
BUS_WIN_L=(210, 230, 255)   # Fenster-Highlight
BUS_GRL = (60,  8,   8)    # Grill dunkel

RMP     = (108, 68,  24)   # Rampe braun
RMP_D   = (72,  44,  12)   # Rampe dunkel
RMP_L   = (140, 90,  36)   # Rampe hell
RMP_NAIL= (180, 160, 60)   # Nagel

OHD     = (52,  52,  64)   # Overhead dunkel
OHD_L   = (72,  72,  88)   # Overhead hell
OHD_D   = (34,  34,  44)   # Overhead sehr dunkel

COIN_G  = (240, 186, 0)    # Gold
COIN_GL = (255, 225, 80)   # Gold hell
COIN_GD = (160, 118, 0)    # Gold dunkel
COIN_S  = (200, 155, 10)   # Gold Symbol

SKIN    = (238, 188, 132)   # Haut
SKIN_D  = (196, 148, 96)   # Haut dunkel
HAIR    = (50,  30,  8)    # Haare
EYE_W   = (240, 240, 240)   # Auge weiß
EYE_C   = (40,  70,  200)  # Auge Iris
EYE_P   = (8,   8,   8)    # Pupille
MOUTH   = (160, 80,  60)   # Mund

JAC     = (36,  112, 218)   # Jacke blau
JAC_D   = (22,  78,  160)   # Jacke dunkel
JAC_L   = (60,  140, 240)   # Jacke hell
PANT    = (24,  52,  140)   # Hose
PANT_D  = (14,  34,  100)   # Hose dunkel

PKG     = (192, 40,  40)   # Rucksack rot
PKG_D   = (136, 22,  22)   # Rucksack dunkel
PKG_ZIP = (200, 170, 50)   # Reißverschluss

BLDG    = (48,  50,  84)   # Gebäude blau-grau
BLDG_D  = (32,  34,  60)   # Gebäude dunkel (Mörtel)
BLDG_L  = (62,  66,  108)  # Gebäude hell
WIN_YEL = (220, 198, 84)   # Fenster beleuchtet
WIN_OFF = (26,  30,  52)   # Fenster dunkel (aus)

SKY_T   = (22,  44,  110)   # Himmel oben (dunkel)
SKY_M   = (44,  88,  170)   # Himmel mitte
SKY_B   = (80,  130, 210)   # Himmel unten (hell)
STAR    = (230, 230, 240)   # Stern


# ── 1. Boden / Asphalt (16×16) ───────────────────────────────────────

def gen_ground():
    i, d = canvas(16, 16, ASP)
    # Helle Kiesel-Pixel
    for x, y in [(2,1),(7,0),(11,3),(4,7),(13,5),(1,11),(9,10),(6,4),(14,2),(3,13),(8,8),(12,14)]:
        px(d, x, y, ASP_L)
    # Dunkle Asphalt-Punkte (Körnung)
    for x, y in [(5,2),(10,6),(0,9),(15,12),(7,15),(3,5),(12,11)]:
        px(d, x, y, ASP_D)
    # Kurzer Riss
    for y in range(3, 7):
        px(d, 9, y, ASP_D)
    save(i, 'ground.png')


# ── 2. Spurmarkierung (4×16) ─────────────────────────────────────────

def gen_lanemark():
    i, d = canvas(4, 16, MARK)
    block(d, 0, 0, 3, 1, (180, 180, 170))   # leicht dunklere Kante
    block(d, 0, 14, 3, 15, (180, 180, 170))
    save(i, 'lanemark.png')


# ── 3. Zug / Bus – Seite (16×16, wird gekachelt) ─────────────────────

def gen_train():
    i, d = canvas(16, 16, BUS)
    # Obere Kante (Dach-Übergang)
    row(d, 0,  16, BUS_D)
    # Zierstreifen (gelb)
    row(d, 3,  16, BUS_YEL)
    # Unterer Schattenstreifen
    row(d, 10, 16, BUS_D)
    row(d, 11, 16, BUS_D)
    # Bodenkante
    row(d, 15, 16, BUS_D)
    # Paneelnaht (senkrecht – wird beim Kacheln sichtbar)
    for y in range(1, 15):
        px(d, 0,  y, BUS_D)
        px(d, 15, y, BUS_D)
    # Kleine Nieten
    for y in [1, 14]:
        for x in [3, 12]:
            px(d, x, y, BUS_D)
    save(i, 'train.png')


# ── 4. Zug-Vorderseite (32×32) ───────────────────────────────────────

def gen_train_front():
    i, d = canvas(32, 32, BUS)
    # Dunkle Rahmenkante
    block(d, 0, 0, 31, 1,  BUS_D)
    block(d, 0, 0, 1,  31, BUS_D)
    block(d, 30, 0, 31, 31, BUS_D)
    block(d, 0, 30, 31, 31, BUS_D)
    # Frontscheibe (obere Hälfte, dunkel)
    block(d, 4,  2, 27, 13, BUS_GRL)
    block(d, 6,  3, 25, 12, (20, 28, 45))  # blauer Glanz
    # Windschutzscheiben-Highlight
    block(d, 8,  4, 14,  7, (80, 100, 160, 140))
    # Zierstreifen
    block(d, 2, 14, 29, 15, BUS_YEL)
    # Kühlergrill (Mitte)
    block(d, 10, 17, 21, 27, BUS_GRL)
    for gy in range(19, 27, 2):
        for gx in range(11, 22, 2):
            px(d, gx, gy, (30, 4, 4))
    # Scheinwerfer (zwei Rechtecke)
    block(d, 3, 23, 8, 28, BUS_YEL)
    block(d, 3, 24, 7, 27, (255, 245, 180))  # Glanz
    block(d, 23, 23, 28, 28, BUS_YEL)
    block(d, 24, 24, 28, 27, (255, 245, 180))
    save(i, 'train_front.png')


# ── 5. Zug-Fenster (16×16) ───────────────────────────────────────────

def gen_train_window():
    i, d = canvas(16, 16, BUS_WIN)
    # Rahmen
    block(d, 0, 0, 15, 1,  BUS_D)
    block(d, 0, 0, 1,  15, BUS_D)
    block(d, 14, 0, 15, 15, BUS_D)
    block(d, 0, 14, 15, 15, BUS_D)
    # Innen-Highlight (oben links)
    block(d, 2, 2, 7, 5, BUS_WIN_L)
    # Unterer Innen-Schatten
    block(d, 2, 10, 13, 13, (110, 140, 170))
    save(i, 'train_window.png')


# ── 6. Rampe (16×16) ─────────────────────────────────────────────────

def gen_ramp():
    i, d = canvas(16, 16, RMP)
    # Holzplanken (4 px hoch, abwechselnd)
    planks = [RMP_L, RMP, RMP_D, RMP]
    for pi, col in enumerate(planks):
        block(d, 0, pi * 4, 15, pi * 4 + 3, col)
    # Maserung-Linien
    for pi in range(4):
        py_base = pi * 4
        px(d, 5,  py_base + 1, RMP_D)
        px(d, 10, py_base + 2, RMP_D)
    # Bretter-Trennlinien
    for y in [3, 7, 11]:
        row(d, y, 16, RMP_D)
    # Nägel
    for nx, ny in [(2, 1), (13, 5), (3, 9), (12, 13)]:
        px(d, nx, ny, RMP_NAIL)
    save(i, 'ramp.png')


# ── 7. Overhead-Balken (16×8) ────────────────────────────────────────

def gen_overhead():
    i, d = canvas(16, 8, OHD)
    # Obere Fläche heller
    row(d, 0, 16, OHD_L)
    row(d, 1, 16, OHD_L)
    # Untere Kante dunkler
    row(d, 6, 16, OHD_D)
    row(d, 7, 16, OHD_D)
    # Senkrechte Strukturlinien
    for x in [0, 7, 15]:
        for y in range(2, 6):
            px(d, x, y, OHD_D)
    save(i, 'overhead.png')


# ── 8. Münze (16×16, transparenter Hintergrund) ──────────────────────

def gen_coin():
    i = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(i)
    # Äußerer Goldring
    d.ellipse([0, 0, 15, 15], fill=(*COIN_G, 255), outline=(*COIN_GD, 255))
    # Innerer Glanz-Bereich
    d.ellipse([2, 2, 12, 12], fill=(*COIN_GL, 255))
    # $ Zeichen (grob pixel-art)
    for y in range(3, 13):
        px(d, 8, y, COIN_S)
    for x in range(4, 12):
        px(d, x, 5, COIN_S)
        px(d, x, 9, COIN_S)
    px(d, 3, 6, COIN_S); px(d, 3, 7, COIN_S); px(d, 3, 8, COIN_S)
    px(d, 12, 8, COIN_S); px(d, 12, 9, COIN_S); px(d, 12, 10, COIN_S)
    save(i, 'coin.png')


# ── 9. Spieler-Körper (16×32) ────────────────────────────────────────
# Obere 16 Zeilen: Jacke. Untere 16 Zeilen: Hose.
# Layout: Vorderseite zentriert (x 4-11), Seiten (0-3, 12-15), Rücken außen.

def gen_player():
    i, d = canvas(16, 32, JAC)
    # ── Oberer Teil: Jacke ────────────────────────────────────────────
    # Seiten dunkler (Schatten)
    block(d, 0,  0,  1,  15, JAC_D)
    block(d, 14, 0,  15, 15, JAC_D)
    # Oberkante (Schultern) leicht hell
    row(d, 0, 16, JAC_L)
    # Reißverschluss-Linie (Mitte)
    for y in range(1, 14):
        px(d, 7, y, JAC_D)
        px(d, 8, y, JAC_D)
    # Ärmel-Naht (gepunktet)
    for y in range(2, 14, 3):
        px(d, 3, y, JAC_D)
        px(d, 12, y, JAC_D)
    # Kragen
    block(d, 5, 0, 10, 1, (200, 200, 210))

    # ── Unterer Teil: Hose ────────────────────────────────────────────
    block(d, 0,  16, 15, 31, PANT)
    # Bein-Trennlinie
    for y in range(17, 32):
        px(d, 7, y, PANT_D)
        px(d, 8, y, PANT_D)
    # Seiten dunkler
    block(d, 0,  16, 1,  31, PANT_D)
    block(d, 14, 16, 15, 31, PANT_D)
    # Hosenbund
    row(d, 16, 16, JAC_D)
    row(d, 17, 16, PANT_D)
    save(i, 'player.png')


# ── 10. Kopf / Haut (16×16) ──────────────────────────────────────────
# UV-Projektion des Ursina-Sphere-Kopfs: oben = Kopfscheitel, Mitte = Gesicht.

def gen_skin():
    i, d = canvas(16, 16, SKIN)
    # Haare (obere 4 Zeilen)
    block(d, 0, 0, 15, 4, HAIR)
    # Seitliche Haare
    block(d, 0, 5, 1, 10, HAIR)
    block(d, 14, 5, 15, 10, HAIR)
    # Wangen etwas dunkler
    block(d, 2, 10, 5, 14, SKIN_D)
    block(d, 10, 10, 13, 14, SKIN_D)
    # Linkes Auge
    block(d, 4, 7, 6, 9, EYE_W)
    px(d, 5, 8, EYE_C)
    # Rechtes Auge
    block(d, 9, 7, 11, 9, EYE_W)
    px(d, 10, 8, EYE_C)
    # Nase
    px(d, 7, 10, SKIN_D)
    px(d, 8, 10, SKIN_D)
    # Mund
    for x in range(5, 11):
        px(d, x, 13, MOUTH)
    px(d, 5,  12, MOUTH)
    px(d, 10, 12, MOUTH)
    # Kinn
    row(d, 15, 16, SKIN_D)
    save(i, 'skin.png')


# ── 11. Rucksack (16×16) ─────────────────────────────────────────────

def gen_backpack():
    i, d = canvas(16, 16, PKG)
    # Rand
    block(d, 0,  0, 1,  15, PKG_D)
    block(d, 14, 0, 15, 15, PKG_D)
    block(d, 0,  0, 15, 1,  PKG_D)
    block(d, 0, 14, 15, 15, PKG_D)
    # Vordertasche
    block(d, 2, 8, 13, 13, PKG_D)
    block(d, 3, 9, 12, 12, (160, 28, 28))
    # Reißverschluss der Tasche
    for x in range(3, 13):
        px(d, x, 8, PKG_ZIP)
    px(d, 7, 7, PKG_ZIP)
    px(d, 8, 7, PKG_ZIP)
    # Träger-Andeutung (heller Streifen)
    block(d, 3, 1, 5, 6, (210, 60, 60))
    block(d, 10, 1, 12, 6, (210, 60, 60))
    save(i, 'backpack.png')


# ── 12. Gebäude-Fassade (16×32) ──────────────────────────────────────

def gen_building():
    i, d = canvas(16, 32, BLDG)
    # Mörtel-Raster (versetzt, Minecraft-Stein-Muster)
    # Gerade Reihen
    for row_y in [0, 8, 16, 24]:
        row(d, row_y, 16, BLDG_D)
        for col_x in [0, 8]:
            block(d, col_x, row_y + 1, col_x + 7, row_y + 7, BLDG_L)
    # Ungerade Reihen (versetzt)
    for row_y in [4, 12, 20, 28]:
        row(d, row_y, 16, BLDG_D)
        for col_x in [-4, 4, 12]:
            x0, x1 = max(0, col_x), min(15, col_x + 7)
            if x1 > x0:
                block(d, x0, row_y + 1, x1, row_y + 3, BLDG_L)
    # Fenster (zufällig beleuchtet, deterministisch)
    win_pattern = [(2, 2, True), (10, 2, False), (2, 10, True),
                   (10, 10, True), (2, 18, False), (10, 18, True),
                   (2, 26, True), (10, 26, False)]
    for wx, wy, lit in win_pattern:
        fc = WIN_YEL if lit else WIN_OFF
        block(d, wx, wy, wx + 4, wy + 5, fc)
        if lit:
            block(d, wx + 1, wy + 1, wx + 2, wy + 2, (255, 235, 140))
    save(i, 'building.png')


# ── 13. Himmel (64×128) – Sphere-Textur ──────────────────────────────
# Gestufte Bänder statt glatter Gradient für Pixel-Art Look.
# Obere Hälfte = Nacht/Dämmerung, untere Hälfte = Tageshimmel.

def gen_sky():
    i, d = canvas(64, 128, SKY_T)
    bands = [
        (0,   16, SKY_T),
        (16,  36, (32, 60, 130)),
        (36,  56, (44, 84, 165)),
        (56,  80, SKY_M),
        (80,  104,(62, 108, 190)),
        (104, 128, SKY_B),
    ]
    for y0, y1, col in bands:
        block(d, 0, y0, 63, y1 - 1, col)
    # Sterne (obere 40 Pixel)
    star_positions = [
        (5,3),(17,1),(29,7),(43,2),(58,5),(11,12),(35,9),(50,14),
        (7,18),(22,15),(40,20),(55,11),(3,25),(31,22),(48,28),(62,19),
        (14,32),(26,30),(44,35),(59,38),(8,8),(36,4),(52,25),
    ]
    for sx, sy in star_positions:
        px(d, sx, sy, STAR)
        px(d, sx, sy, STAR)
    # Hellere Hauptsterne (2×2)
    for sx, sy in [(17, 1), (43, 2), (55, 11), (7, 18)]:
        block(d, sx, sy, sx + 1, sy + 1, STAR)
    save(i, 'sky.png')


# ── barrier.png erhalten (kein Spielobjekt mehr, aber Dateipfad bleibt) ─

def gen_barrier_placeholder():
    """Leere 1×1 Textur – Datei wird nicht mehr genutzt, schadet aber nicht."""
    i = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    save(i, 'barrier.png')


# ── Spieler-Figur: 6-Plane Faces (je 16×16) ──────────────────────────
# Konvention: 'f' = -Z-Seite (Kamera / Charakter-Rücken),
#             'b' = +Z-Seite (Laufrichtung / Charakter-Front)

def gen_body_faces():
    """Torso (Jacke blau) – 6 Seiten"""
    i, d = canvas(16, 16, JAC)          # f: Rücken der Jacke (Kamera-Seite)
    block(d, 0, 0, 1, 15, JAC_D); block(d, 14, 0, 15, 15, JAC_D)
    row(d, 0, 16, JAC_L); row(d, 15, 16, JAC_D)
    block(d, 4, 1, 5, 14, JAC_L); block(d, 10, 1, 11, 14, JAC_L)
    save(i, 'body_f.png')

    i, d = canvas(16, 16, JAC)          # b: Vorderseite – Reißverschluss
    block(d, 0, 0, 1, 15, JAC_D); block(d, 14, 0, 15, 15, JAC_D)
    row(d, 0, 16, JAC_L); row(d, 15, 16, JAC_D)
    block(d, 5, 0, 10, 1, (200, 200, 210))
    for y in range(2, 14): px(d, 7, y, JAC_D); px(d, 8, y, (200, 200, 210))
    save(i, 'body_b.png')

    for name in ('body_l.png', 'body_r.png'):
        i, d = canvas(16, 16, JAC_D); row(d, 0, 16, JAC); save(i, name)

    i, d = canvas(16, 16, JAC); row(d, 0, 16, JAC_L); save(i, 'body_t.png')
    i, d = canvas(16, 16, JAC_D); save(i, 'body_bot.png')


def gen_head_faces():
    """Kopf – 6 Seiten"""
    i, d = canvas(16, 16, SKIN)         # f: Hinterkopf (was Kamera sieht)
    block(d, 0, 0, 15, 5, HAIR)
    block(d, 0, 0, 2, 15, HAIR); block(d, 13, 0, 15, 15, HAIR)
    row(d, 15, 16, SKIN_D)
    save(i, 'head_f.png')

    i, d = canvas(16, 16, SKIN)         # b: Gesicht (Laufrichtung)
    block(d, 0, 0, 15, 5, HAIR)
    block(d, 0, 0, 2, 15, HAIR); block(d, 13, 0, 15, 15, HAIR)
    block(d, 2, 10, 5, 14, SKIN_D); block(d, 10, 10, 13, 14, SKIN_D)
    block(d, 4, 7, 6, 9, EYE_W); px(d, 5, 8, EYE_C); px(d, 5, 8, EYE_P)
    block(d, 9, 7, 11, 9, EYE_W); px(d, 10, 8, EYE_C); px(d, 10, 8, EYE_P)
    px(d, 7, 10, SKIN_D); px(d, 8, 10, SKIN_D)
    for x in range(5, 11): px(d, x, 13, MOUTH)
    save(i, 'head_b.png')

    for name in ('head_l.png', 'head_r.png'):
        i, d = canvas(16, 16, SKIN)
        block(d, 0, 0, 15, 5, HAIR); block(d, 0, 0, 2, 15, HAIR)
        block(d, 5, 7, 9, 9, EYE_W); px(d, 7, 8, EYE_C)
        save(i, name)

    i, d = canvas(16, 16, HAIR); save(i, 'head_t.png')
    i, d = canvas(16, 16, SKIN_D); row(d, 0, 16, SKIN); save(i, 'head_bot.png')


def gen_leg_faces():
    """Beine (beide teilen dieselben Texturen) – 6 Seiten"""
    i, d = canvas(16, 16, PANT)         # f: Hosenrückseite
    block(d, 0, 0, 1, 15, PANT_D); block(d, 14, 0, 15, 15, PANT_D)
    save(i, 'leg_f.png')

    i, d = canvas(16, 16, PANT)         # b: Hosenvorderseite – Knie-Naht
    block(d, 0, 0, 1, 15, PANT_D); block(d, 14, 0, 15, 15, PANT_D)
    row(d, 8, 16, PANT_D)
    save(i, 'leg_b.png')

    for name in ('leg_l.png', 'leg_r.png'):
        i, d = canvas(16, 16, PANT_D); row(d, 0, 16, PANT); save(i, name)

    i, d = canvas(16, 16, PANT_D); save(i, 'leg_t.png')
    i, d = canvas(16, 16, (22, 22, 22)); save(i, 'leg_bot.png')   # Schuh-Unterseite


def gen_pack_faces():
    """Rucksack (rot) – 6 Seiten"""
    i, d = canvas(16, 16, PKG)          # f: Außenseite (Kamera) – Tasche sichtbar
    block(d, 0, 0, 1, 15, PKG_D); block(d, 14, 0, 15, 15, PKG_D)
    block(d, 0, 0, 15, 1, PKG_D); block(d, 0, 14, 15, 15, PKG_D)
    block(d, 2, 8, 13, 13, PKG_D); block(d, 3, 9, 12, 12, (160, 28, 28))
    for x in range(3, 13): px(d, x, 8, PKG_ZIP)
    block(d, 3, 2, 5, 7, (210, 60, 60)); block(d, 10, 2, 12, 7, (210, 60, 60))
    save(i, 'pack_f.png')

    i, d = canvas(16, 16, PKG_D)        # b: liegt am Spielerrücken an
    for x in range(3, 13): px(d, x, 3, PKG_ZIP); px(d, x, 12, PKG_ZIP)
    save(i, 'pack_b.png')

    for name in ('pack_l.png', 'pack_r.png'):
        i, d = canvas(16, 16, PKG_D); row(d, 0, 16, PKG); save(i, name)

    i, d = canvas(16, 16, PKG_D); row(d, 0, 16, PKG); save(i, 'pack_t.png')
    i, d = canvas(16, 16, PKG_D); save(i, 'pack_bot.png')


# ── Alle generieren ───────────────────────────────────────────────────

if __name__ == '__main__':
    print('Generiere Pixel-Art Texturen (16×16)...')
    gen_ground()
    gen_lanemark()
    gen_train()
    gen_train_front()
    gen_train_window()
    gen_ramp()
    gen_overhead()
    gen_coin()
    gen_building()
    gen_sky()
    gen_barrier_placeholder()
    gen_body_faces()
    gen_head_faces()
    gen_leg_faces()
    gen_pack_faces()
    print(f'\nFertig! Alle Texturen in: {OUT}')
    print('Starte das Spiel – Nearest-Neighbour Filtering ist bereits in subway_surfer.py aktiv.')

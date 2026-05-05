"""
generate_textures.py
Erstellt alle Spiel-Texturen als PNG-Dateien im Ordner textures/.
Einmal ausführen: python generate_textures.py
"""

import os
import random
from PIL import Image, ImageDraw, ImageFilter

random.seed(42)
OUT = os.path.join(os.path.dirname(__file__), 'textures')
os.makedirs(OUT, exist_ok=True)


def save(img: Image.Image, name: str):
    path = os.path.join(OUT, name)
    img.save(path)
    print(f'  {name}')


# ── Hilfsfunktionen ──────────────────────────────────────────────────


def noise_overlay(img: Image.Image, amount: int = 18) -> Image.Image:
    """Fügt leichtes Rauschen auf alle Pixel."""
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r = random.randint(-amount, amount)
            p = px[x, y]
            px[x, y] = tuple(max(0, min(255, c + r)) for c in p[:3]) + (p[3],)
    return img


def make_image(w: int, h: int, bg: tuple) -> tuple:
    img = Image.new('RGBA', (w, h), bg + (255,))
    draw = ImageDraw.Draw(img)
    return img, draw


# ── 1. Boden / Asphalt ───────────────────────────────────────────────

def gen_ground():
    img, draw = make_image(256, 256, (42, 42, 42))
    # Risse
    for _ in range(6):
        x0 = random.randint(0, 255)
        y0 = random.randint(0, 255)
        length = random.randint(20, 60)
        angle_x = random.choice([-1, 0, 1])
        for i in range(length):
            px = x0 + angle_x * i
            py = y0 + i
            if 0 <= px < 256 and 0 <= py < 256:
                draw.point((px, py), fill=(28, 28, 28, 255))
    # Kieselsteine (helle Punkte)
    for _ in range(120):
        x = random.randint(0, 255)
        y = random.randint(0, 255)
        c = random.randint(55, 75)
        draw.point((x, y), fill=(c, c, c, 255))
    noise_overlay(img, 12)
    save(img, 'ground.png')


# ── 2. Spurmarkierung ────────────────────────────────────────────────

def gen_lanemark():
    img, draw = make_image(16, 128, (200, 200, 200))
    noise_overlay(img, 10)
    save(img, 'lanemark.png')


# ── 3. Barriere (orange Straßensperre) ──────────────────────────────

def gen_barrier():
    img, draw = make_image(256, 128, (255, 130, 0))
    stripe_w = 28
    for i in range(-2, 12):
        x0 = i * stripe_w * 2
        pts = [(x0, 0), (x0 + stripe_w, 0), (x0 + stripe_w + 128, 128), (x0 + 128, 128)]
        draw.polygon(pts, fill=(230, 230, 230, 255))
    # Rote Reflexstreifen
    draw.rectangle([0, 52, 256, 76], fill=(200, 40, 40, 255))
    draw.rectangle([0, 20, 256, 32], fill=(180, 30, 30, 180))
    draw.rectangle([0, 96, 256, 108], fill=(180, 30, 30, 180))
    noise_overlay(img, 10)
    save(img, 'barrier.png')


# ── 4. Zug-Körper ────────────────────────────────────────────────────

def gen_train():
    img, draw = make_image(512, 256, (190, 30, 30))
    # Paneel-Linien (vertikal)
    for x in range(0, 512, 64):
        draw.line([(x, 0), (x, 256)], fill=(140, 15, 15, 255), width=3)
    # Horizontale Streifen
    draw.rectangle([0, 90, 512, 106], fill=(220, 220, 220, 255))
    draw.rectangle([0, 150, 512, 166], fill=(160, 20, 20, 255))
    # Nieten
    for x in range(16, 512, 32):
        for y in [10, 246]:
            draw.ellipse([x-3, y-3, x+3, y+3], fill=(110, 10, 10, 255))
    noise_overlay(img, 8)
    save(img, 'train.png')


# ── 5. Zug-Fenster ───────────────────────────────────────────────────

def gen_train_window():
    img, draw = make_image(64, 64, (220, 200, 100))
    # Fensterrahmen
    draw.rectangle([2, 2, 61, 61], outline=(80, 70, 20, 255), width=3)
    # Spiegelung
    draw.polygon([(8, 8), (24, 8), (10, 30)], fill=(255, 245, 180, 200))
    # Innenreflexion (dunklere Zone)
    draw.rectangle([30, 30, 60, 60], fill=(180, 160, 70, 180))
    noise_overlay(img, 6)
    save(img, 'train_window.png')


# ── 6. Zug-Vorderseite ───────────────────────────────────────────────

def gen_train_front():
    img, draw = make_image(256, 256, (190, 30, 30))
    # Motorhaube Kontur
    draw.rectangle([20, 60, 236, 230], fill=(160, 20, 20, 255), outline=(100, 10, 10, 255), width=4)
    # Scheinwerfer
    for cx in [65, 191]:
        draw.ellipse([cx-22, 170, cx+22, 214], fill=(255, 240, 160, 255), outline=(80, 80, 20, 255), width=3)
        draw.ellipse([cx-10, 180, cx+10, 204], fill=(255, 255, 220, 255))
    # Kühlergrille
    draw.rectangle([90, 80, 166, 150], fill=(80, 10, 10, 255))
    for gy in range(88, 148, 14):
        draw.line([(92, gy), (164, gy)], fill=(40, 5, 5, 255), width=2)
    for gx in range(98, 164, 18):
        draw.line([(gx, 82), (gx, 148)], fill=(40, 5, 5, 255), width=2)
    # Fahrernummer
    draw.rectangle([108, 20, 148, 56], fill=(255, 255, 255, 200))
    noise_overlay(img, 8)
    save(img, 'train_front.png')


# ── 7. Rampe ─────────────────────────────────────────────────────────

def gen_ramp():
    img, draw = make_image(256, 128, (100, 60, 20))
    # Holzplanken (horizontale Streifen)
    plank_cols = [
        (120, 72, 28), (108, 62, 22), (132, 80, 32), (98, 58, 18), (115, 68, 25)
    ]
    ph = 24
    for i, col in enumerate(plank_cols):
        y0 = i * ph
        draw.rectangle([0, y0, 256, y0 + ph - 2], fill=col)
        # Maserung
        for _ in range(8):
            lx = random.randint(0, 255)
            draw.line([(lx, y0+2), (lx + random.randint(10,40), y0 + ph - 4)],
                      fill=(max(0, col[0]-25), max(0, col[1]-20), max(0, col[2]-10), 200), width=1)
    # Schrauben
    for px in [20, 80, 140, 200, 240]:
        for py in [12, 36, 60, 84, 108]:
            draw.ellipse([px-3, py-3, px+3, py+3], fill=(60, 35, 10, 255))
    noise_overlay(img, 10)
    save(img, 'ramp.png')


# ── 8. Overhead-Balken ───────────────────────────────────────────────

def gen_overhead():
    img, draw = make_image(256, 64, (45, 45, 55))
    # Betonstruktur
    for x in range(0, 256, 48):
        draw.line([(x, 0), (x, 64)], fill=(35, 35, 45, 255), width=2)
    # Bewehrungsspuren
    for y in [16, 48]:
        draw.line([(0, y), (256, y)], fill=(55, 55, 65, 255), width=1)
    noise_overlay(img, 14)
    save(img, 'overhead.png')


# ── 9. Tunnel-Wand ───────────────────────────────────────────────────

def gen_tunnel():
    img, draw = make_image(256, 256, (50, 50, 58))
    # Steinblöcke (versetzt)
    bw, bh = 64, 40
    mortar = (35, 35, 42, 255)
    for row in range(7):
        offset = (row % 2) * (bw // 2)
        for col in range(-1, 5):
            x0 = col * bw + offset
            y0 = row * bh
            shade = random.randint(-8, 8)
            bc = (50 + shade, 50 + shade, 58 + shade, 255)
            draw.rectangle([x0+2, y0+2, x0+bw-2, y0+bh-2], fill=bc)
            draw.rectangle([x0, y0, x0+bw, y0+2], fill=mortar)
            draw.rectangle([x0, y0, x0+2, y0+bh], fill=mortar)
    noise_overlay(img, 10)
    save(img, 'tunnel.png')


# ── 10. Münze ────────────────────────────────────────────────────────

def gen_coin():
    img = Image.new('RGBA', (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Äußerer Rand
    draw.ellipse([4, 4, 123, 123], fill=(200, 140, 0, 255), outline=(160, 100, 0, 255), width=4)
    # Innerer Glanz
    draw.ellipse([14, 14, 113, 113], fill=(255, 210, 40, 255))
    # Highlight
    draw.ellipse([30, 25, 75, 65], fill=(255, 245, 160, 200))
    # Dollar-Zeichen (vereinfacht)
    draw.rectangle([59, 20, 67, 108], fill=(200, 140, 0, 200), width=0)
    draw.rectangle([38, 44, 88, 56], fill=(200, 140, 0, 200), width=0)
    draw.rectangle([38, 68, 88, 80], fill=(200, 140, 0, 200), width=0)
    save(img, 'coin.png')


# ── 11. Spieler-Körper ───────────────────────────────────────────────

def gen_player():
    img, draw = make_image(128, 256, (40, 120, 220))
    # Jacken-Streifen (vertikal)
    draw.rectangle([56, 0, 72, 256], fill=(30, 100, 200, 255))
    # Reißverschluss-Linie
    draw.line([(64, 0), (64, 180)], fill=(180, 180, 200, 255), width=2)
    # Ärmelnaht
    for y in range(0, 200, 8):
        draw.point((18, y), fill=(30, 100, 190, 255))
        draw.point((110, y), fill=(30, 100, 190, 255))
    # Hosenbein-Trennung
    draw.line([(64, 180), (64, 256)], fill=(20, 60, 140, 255), width=3)
    draw.rectangle([0, 180, 128, 256], fill=(30, 60, 150, 255))
    noise_overlay(img, 6)
    save(img, 'player.png')


# ── 12. Spieler-Kopf / Haut ──────────────────────────────────────────

def gen_skin():
    img, draw = make_image(128, 128, (240, 190, 140))
    # Haare
    draw.ellipse([10, 0, 118, 55], fill=(60, 35, 10, 255))
    draw.rectangle([10, 20, 118, 55], fill=(60, 35, 10, 255))
    # Augen
    for ex in [38, 88]:
        draw.ellipse([ex-8, 55, ex+8, 73], fill=(255, 255, 255, 255))
        draw.ellipse([ex-4, 58, ex+4, 70], fill=(50, 80, 160, 255))
        draw.ellipse([ex-2, 60, ex+2, 68], fill=(10, 10, 10, 255))
    # Mund
    draw.arc([44, 82, 84, 106], start=10, end=170, fill=(160, 80, 60, 255), width=3)
    noise_overlay(img, 5)
    save(img, 'skin.png')


# ── 13. Rucksack ─────────────────────────────────────────────────────

def gen_backpack():
    img, draw = make_image(128, 128, (200, 50, 50))
    # Hauptfach
    draw.rectangle([10, 10, 118, 118], fill=(180, 35, 35, 255), outline=(120, 20, 20, 255), width=3)
    # Vordertasche
    draw.rectangle([25, 65, 103, 110], fill=(160, 25, 25, 255), outline=(100, 15, 15, 255), width=2)
    # Reißverschluss
    draw.line([(30, 70), (98, 70)], fill=(180, 160, 60, 255), width=3)
    draw.ellipse([60, 66, 70, 76], fill=(200, 180, 80, 255))
    # Träger-Andeutung
    draw.arc([15, 5, 55, 40], start=180, end=360, fill=(130, 20, 20, 255), width=5)
    draw.arc([73, 5, 113, 40], start=180, end=360, fill=(130, 20, 20, 255), width=5)
    noise_overlay(img, 8)
    save(img, 'backpack.png')


# ── 14. Gebäude-Fassade ──────────────────────────────────────────────

def gen_building():
    img, draw = make_image(256, 512, (50, 55, 90))
    # Betonplatten-Raster
    for y in range(0, 512, 80):
        draw.line([(0, y), (256, y)], fill=(40, 44, 72, 255), width=2)
    for x in range(0, 256, 64):
        draw.line([(x, 0), (x, 512)], fill=(40, 44, 72, 255), width=2)
    # Zufällige beleuchtete Fenster
    for wy in range(1, 7):
        for wx in range(1, 4):
            lit = random.random() > 0.35
            fc = (220, 200, 100, 255) if lit else (30, 35, 60, 255)
            x0 = wx * 64 - 48
            y0 = wy * 80 - 56
            draw.rectangle([x0, y0, x0+36, y0+50], fill=fc)
            if lit:
                draw.rectangle([x0+4, y0+4, x0+32, y0+20], fill=(255, 245, 180, 200))
    noise_overlay(img, 8)
    save(img, 'building.png')


# ── 15. Himmel-Gradient ──────────────────────────────────────────────

def gen_sky():
    img, draw = make_image(256, 512, (30, 80, 160))
    for y in range(512):
        t = y / 511
        r = int(30 + t * 10)
        g = int(80 + t * 20)
        b = int(160 - t * 40)
        draw.line([(0, y), (256, y)], fill=(r, g, b, 255))
    # Sterne
    for _ in range(80):
        sx, sy = random.randint(0, 255), random.randint(0, 200)
        br = random.randint(180, 255)
        draw.point((sx, sy), fill=(br, br, br, 255))
    save(img, 'sky.png')


# ── Alle generieren ───────────────────────────────────────────────────

if __name__ == '__main__':
    print('Generiere Texturen...')
    gen_ground()
    gen_lanemark()
    gen_barrier()
    gen_train()
    gen_train_window()
    gen_train_front()
    gen_ramp()
    gen_overhead()
    gen_tunnel()
    gen_coin()
    gen_player()
    gen_skin()
    gen_backpack()
    gen_building()
    gen_sky()
    print(f'Fertig! Alle Texturen in: {OUT}')

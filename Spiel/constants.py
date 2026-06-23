from ursina import Color

# ── Farb-Palette (0-1 Skala) ─────────────────────────────────────────
C_SKY      = Color(0.235, 0.431, 0.706, 1)
C_PLAYER   = Color(0.157, 0.471, 0.863, 1)
C_SKIN     = Color(0.941, 0.745, 0.549, 1)
C_PACK     = Color(0.863, 0.235, 0.235, 1)
C_GROUND   = Color(0.176, 0.176, 0.176, 1)
C_LANEMARK = Color(0.784, 0.784, 0.784, 1)
C_CAR      = Color(0.180, 0.180, 0.210, 1)
C_CABIN    = Color(0.110, 0.110, 0.140, 1)
C_TRAIN    = Color(0.784, 0.118, 0.118, 1)
C_RAMP     = Color(0.600, 0.220, 0.100, 1)
C_OVERHEAD = Color(0.200, 0.200, 0.240, 1)
C_TUNNEL   = Color(0.150, 0.150, 0.170, 1)
C_COIN     = Color(1.000, 0.843, 0.000, 1)
C_WIN_YEL  = Color(0.902, 0.863, 0.510, 1)
C_WIN_RED  = Color(1.000, 0.196, 0.196, 1)
C_BLDG     = [
    Color(0.196, 0.216, 0.353, 1),
    Color(0.275, 0.255, 0.431, 1),
    Color(0.157, 0.196, 0.314, 1),
    Color(0.314, 0.275, 0.392, 1),
]
C_AMBIENT  = Color(0.27, 0.29, 0.39, 1)

# ── Spurlayout ───────────────────────────────────────────────────────
LANES      = [-2.5, 0.0, 2.5]
LANE_COUNT = 3

# ── Welt ─────────────────────────────────────────────────────────────
SPAWN_Z    = 50
DESPAWN_Z  = -14
TILE_LEN   = 12
TILE_COUNT = 10

# ── Spielgeschwindigkeit ──────────────────────────────────────────────
INITIAL_SPD = 8.0
SPEED_INC   = 0.002

# ── Spieler ───────────────────────────────────────────────────────────
# Sprung: kalibriert so dass Spieler Autos (Dach 1.3) locker überspringt,
# Züge (top=2.2) aber NICHT erreicht (nur über die Rampe).
# max_height = JUMP_VEL² / (2*|GRAVITY|) = 67.24/36 = 1.868
# Spieler-Boden max = 0.75 + 1.868 - 0.48 = 2.14 < Zug-Top 2.2  ✓
JUMP_VEL      = 8.2
GRAVITY       = -18.0
SLIDE_DUR     = 1.5
LANE_SPD      = 18.0
PLAYER_BASE_Y = 0.75
PLAYER_SY     = 1.0     # Körperhöhe
PLAYER_HW     = 0.32    # halbe Breite (für Kollision)
PLAYER_HH     = 0.48    # Faktor × scale_y = halbe Höhe

# ── Auto ──────────────────────────────────────────────────────────────
CAR_SX   = 2.0
CAR_SY   = 1.2
CAR_Y    = 0.6
CAR_CAB_TOP = 1.3   # Oberkante Fahrerkabine = Kollisions- & Lande-Höhe (solide, kein Durchlaufen)
CAR_TOP  = CAR_CAB_TOP

# ── Zug ───────────────────────────────────────────────────────────────
TRAIN_SX   = 2.2
TRAIN_SY   = 2.2
TRAIN_Y    = 1.1
TRAIN_TOP  = TRAIN_Y + TRAIN_SY * 0.5   # = 2.2  (Oberkante)
RAMP_LEN   = 2.5   # Länge der Rampe vor dem Zug

# Overhead-Hindernis: nur durch Sliden passierbar
# Boden = OVERHEAD_Y - OVERHEAD_SY/2 = 2.8 - 2.0 = 0.8
# Slide-Top ≈ 0.70 < 0.8 → passiert ✓  |  Stand-Top ≈ 1.25 > 0.8 → kollidiert ✓
OVERHEAD_Y  = 2.8
OVERHEAD_SY = 4.0

# ── Leben & Kollision ─────────────────────────────────────────────────
MAX_LIVES    = 3
INVINCIBLE   = 2.0    # Sekunden Unverwundbarkeit nach Treffer

# Pushback: deutlich länger & weiter für Gestensteuerung
PUSHBACK_DUR  = 1.6   # Sekunden für Zurückzieh-Animation
PUSHBACK_DIST = 12.0  # Einheiten zurück

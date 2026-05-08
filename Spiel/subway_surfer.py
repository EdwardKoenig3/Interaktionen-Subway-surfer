"""
Subway Surfer – 3D Prototype
Einstiegspunkt: python subway_surfer.py

Dateistruktur:
    constants.py    – Farben und Spielkonstanten
    game_state.py   – GS (globaler Spielzustand)
    player.py       – Player (Physik, Steuerung, Pushback)
    obstacles.py    – Obstacle (Auto, Zug, Overhead)
    coins.py        – Coin
    world.py        – GroundTile, make_buildings
    hud.py          – HUD-Elemente, update_hearts
    subway_surfer.py– App, Spawn, Kollision, Update, Input

Gesture-Interface:
    player.action_left()   player.action_right()
    player.action_jump()
    player.start_slide()   – Slide beginnen (Pose eingenommen)
    player.stop_slide()    – Slide beenden  (Pose verlassen)
    player.action_slide()  – Einmaliger Slide ohne Hold (OSC-Fallback)
"""

import random, sys, math
from ursina import *
from osc_input import start_osc_server, poll_actions

from constants import (
    C_SKY, C_AMBIENT,
    LANES, LANE_COUNT, SPAWN_Z, DESPAWN_Z,
    TILE_LEN, TILE_COUNT,
    SPEED_INC, JUMP_VEL, GRAVITY,
    PLAYER_BASE_Y, PLAYER_SY,
    TRAIN_TOP,
    MAX_LIVES, INVINCIBLE,
)
from game_state  import GS
from player      import Player
from obstacles   import Obstacle
from coins       import Coin
from world       import GroundTile, SidewalkTile, make_buildings
from hud         import create_hud, update_hearts

# ── App ──────────────────────────────────────────────────────────────
app = Ursina(title='Subway Surfer 3D', vsync=True)

# Pixel-Art Textur-Filterung: Loader monkey-patchen → alle Texturen nearest-neighbour
from panda3d.core import SamplerState as _SS
_orig_load = app.loader.loadTexture
def _px_load(*a, **kw):
    t = _orig_load(*a, **kw)
    if t:
        t.setMagfilter(_SS.FT_nearest)
        t.setMinfilter(_SS.FT_nearest)
    return t
app.loader.loadTexture = _px_load

window.color = C_SKY
Entity(model='sphere', texture='textures/sky.png', scale=300,
       double_sided=True, unlit=True, eternal=True)

# ── HUD ──────────────────────────────────────────────────────────────
hud_score, hud_coins, hud_hint, hud_over, hud_sub, hud_restart, hearts, \
    hud_pause_bg, hud_pause_title, hud_pause_sub, hud_logo = create_hud()

# ── Globale Listen ────────────────────────────────────────────────────
obstacles: list[Obstacle] = []
coins:     list[Coin]     = []
tiles:     list[GroundTile] = []
player:    Player | None  = None


# ── Spawn ─────────────────────────────────────────────────────────────

def _spawn_obstacle():
    kind = random.choices(
        ['car', 'train', 'train_long', 'train_xl', 'overhead'],
        weights=[3, 6, 3, 1, 2]
    )[0]
    obstacles.append(Obstacle(random.randint(0, LANE_COUNT - 1), kind))


def _spawn_coins():
    lane = random.randint(0, LANE_COUNT - 1)
    mode = random.choices(['line', 'arc', 'high'], weights=[4, 4, 2])[0]

    if mode == 'arc':
        # Münzen entlang der Sprung-Parabel
        T = 2 * JUMP_VEL / abs(GRAVITY)
        n = 7
        for i in range(n):
            t = T * i / (n - 1)
            y = PLAYER_BASE_Y + JUMP_VEL * t + 0.5 * GRAVITY * t ** 2
            z = SPAWN_Z + GS.speed * t
            coins.append(Coin(lane, z, y=max(y, PLAYER_BASE_Y + 0.1)))
    elif mode == 'high':
        for i in range(random.randint(3, 5)):
            coins.append(Coin(lane, SPAWN_Z + i * 1.8, y=TRAIN_TOP + 0.45))
    else:
        for i in range(random.randint(3, 6)):
            coins.append(Coin(lane, SPAWN_Z + i * 1.7, y=1.0))


# ── Kollision ─────────────────────────────────────────────────────────

def _check_collisions():
    # ── Plattform-Landing: Zug-Dach und Auto-Dach ────────────────────
    if player.is_jumping and player.vel_y <= 0:
        phw, phh = player.half_extents()
        player_bottom = player.y - phh
        for o in obstacles:
            if o._dead or not o.has_platform:
                continue
            if abs(o.x - player.x) >= o.hw + phw - 0.05:
                continue
            if abs(o.z - player.z) >= o.hz + 0.4:
                continue
            plat_top  = o.y + o.hh
            tol_down  = 1.0 if o.has_ramp else 0.5
            if player_bottom <= plat_top + 0.3 and player_bottom >= plat_top - tol_down:
                player.y          = plat_top + phh
                player.vel_y      = 0.0
                player.is_jumping = False
                player.platform   = o
                player._ramp_jump = False
                break

    # ── Körper-Kollision mit Hindernissen ─────────────────────────────
    if not GS.is_invincible():
        hit = False
        for o in obstacles:
            if o._dead:
                continue
            # Rampen-Zug: in der Boost-Zone übernimmt der Rampen-Boost
            # (auch im Slide → Slide wird abgebrochen und Spieler hochgeboostet).
            # Damit kein "durch die Treppe sliden + Schaden".
            if o.has_ramp and abs(o.x - player.x) < o.hw + 0.5:
                train_front = o.z - o.hz
                in_ramp_zone = 0.3 <= train_front <= 3.3
                if player._ramp_jump or in_ramp_zone:
                    continue
            if o.hits_body(player):
                hit = True
                break
        if hit:
            GS.lives    -= 1
            GS.inv_timer = INVINCIBLE
            GS.shake_t   = 0.5
            update_hearts(hearts, GS.lives)
            player.pushback()
            if GS.lives <= 0:
                GS.running = False
                _show_game_over()
                return

    # ── Münzen einsammeln ─────────────────────────────────────────────
    for c in coins[:]:
        if c.collect(player):
            c._dead   = True
            GS.coins += 1
            destroy(c)
            coins.remove(c)
            # Alle 50 Münzen → 1 Herz zurück (gedeckelt bei MAX_LIVES)
            if GS.coins % 50 == 0 and GS.lives < MAX_LIVES:
                GS.lives += 1
                update_hearts(hearts, GS.lives)

    # ── Tote Entities entfernen ───────────────────────────────────────
    obstacles[:] = [o for o in obstacles if not o._dead]
    coins[:]     = [c for c in coins     if not c._dead]


# ── Game Over / Neustart ──────────────────────────────────────────────

def _show_game_over():
    hud_over.text    = 'GAME OVER'
    hud_sub.text     = f'Score: {GS.score}   Münzen: {GS.coins}'
    hud_restart.text = 'R  –  Neustart'
    hud_hint.enabled = False


def _reset():
    global obstacles, coins, tiles, player

    for o in obstacles:
        for d in o._deco: destroy(d)
        destroy(o)
    for c in coins:  destroy(c)
    for ti in tiles: destroy(ti)
    if player: destroy(player)

    obstacles.clear(); coins.clear(); tiles.clear()

    GS.reset()
    update_hearts(hearts, MAX_LIVES)
    hud_over.text = ''; hud_sub.text = ''; hud_restart.text = ''
    hud_hint.enabled = True

    player = Player()
    player.obstacles_ref = obstacles   # Referenz für Wandkollision

    for i in range(TILE_COUNT):
        z = i * TILE_LEN - TILE_LEN
        tiles.append(GroundTile(z))
        tiles.append(SidewalkTile(z, -1))
        tiles.append(SidewalkTile(z, +1))


# ── Haupt-Update ──────────────────────────────────────────────────────

def _set_pause(paused: bool):
    GS.paused = paused
    hud_pause_bg.enabled  = paused
    hud_pause_sub.enabled = paused
    hud_logo.enabled      = paused
    if paused:
        # Unterscheide: noch nie gestartet vs. mitten im Spiel pausiert
        if GS.elapsed == 0.0:
            # Start-Bildschirm: Logo zeigt den Titel, kein zusätzlicher Text
            hud_pause_title.enabled = False
            hud_pause_title.text    = ''
            hud_pause_sub.text      = 'ENTER  –  Starten'
        else:
            hud_pause_title.enabled = True
            hud_pause_title.text    = 'PAUSE'
            hud_pause_sub.text      = 'ENTER  –  Weiter'
    else:
        hud_pause_title.enabled = False


def update():
    if not GS.running or GS.paused:
        return
    dt = time.dt

    GS.elapsed    += dt
    GS.speed      += SPEED_INC
    GS.score       = int(GS.elapsed * GS.speed * 2)
    if GS.inv_timer > 0: GS.inv_timer = max(0.0, GS.inv_timer - dt)
    if GS.shake_t  > 0: GS.shake_t   = max(0.0, GS.shake_t   - dt)

    hud_score.text = str(GS.score)
    hud_coins.text = f'$ {GS.coins}'

    # Kamera: sanft Spieler-X folgen + Shake nach Treffer
    cam_x = player.x * 0.25
    if GS.shake_t > 0:
        cam_x += random.uniform(-0.45, 0.45) * (GS.shake_t / 0.5)
    camera.x = lerp(camera.x, cam_x, min(7 * dt, 1))
    # Kamera-Z leicht mit Pushback mitbewegen
    camera.z = lerp(camera.z, -13 + player.z * 0.35, min(10 * dt, 1))

    GS.obs_timer += dt
    if GS.obs_timer >= GS.obs_interval():
        _spawn_obstacle()
        GS.obs_timer = 0

    GS.coin_timer += dt
    if GS.coin_timer >= 1.2:
        _spawn_coins()
        GS.coin_timer = 0

    poll_actions(player)
    _check_collisions()


# ── Eingabe ───────────────────────────────────────────────────────────

def input(key):
    if not GS.running:
        if key == 'r':
            _reset()
            _set_pause(True)
        return
    if key == 'enter':
        _set_pause(not GS.paused)
        return
    if key == 'p':
        _set_pause(not GS.paused)
        return
    if GS.paused:
        return
    if key in ('left arrow',  'a'):                 player.action_left()
    if key in ('right arrow', 'd'):                 player.action_right()
    if key in ('up arrow', 'w', 'space'):           player.action_jump()
    if key in ('down arrow', 's'):                  player.start_slide()
    if key in ('down arrow up', 's up'):            player.stop_slide()
    if key == 'escape':                    sys.exit()


# ── Szene aufbauen ────────────────────────────────────────────────────

camera.position   = (0, 4.5, -13)
camera.rotation_x = 16

DirectionalLight(direction=(1, -2, 1), color=color.white)
AmbientLight(color=C_AMBIENT)

make_buildings()
_reset()
_set_pause(True)
start_osc_server()
app.run()

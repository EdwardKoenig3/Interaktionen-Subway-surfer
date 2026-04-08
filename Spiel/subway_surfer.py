"""
Subway Surfer – 3D Prototype
Einstiegspunkt: python subway_surfer.py

Dateistruktur:
    constants.py    – Farben und Spielkonstanten
    game_state.py   – GS (globaler Spielzustand)
    player.py       – Player (Physik, Steuerung, Pushback)
    obstacles.py    – Obstacle, TunnelObstacle
    coins.py        – Coin
    world.py        – GroundTile, make_buildings
    hud.py          – HUD-Elemente, update_hearts
    subway_surfer.py– App, Spawn, Kollision, Update, Input

Gesture-Interface:
    player.action_left()   player.action_right()
    player.action_jump()   player.action_slide()
"""

import random, sys, math
from ursina import *

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
from obstacles   import Obstacle, TunnelObstacle
from coins       import Coin
from world       import GroundTile, make_buildings
from hud         import create_hud, update_hearts

# ── App ──────────────────────────────────────────────────────────────
app = Ursina(title='Subway Surfer 3D', vsync=True)
window.color = C_SKY
Entity(model='sphere', color=C_SKY, scale=300,
       double_sided=True, unlit=True, eternal=True)

# ── HUD ──────────────────────────────────────────────────────────────
hud_score, hud_coins, hud_hint, hud_over, hud_sub, hud_restart, hearts = create_hud()

# ── Globale Listen ────────────────────────────────────────────────────
obstacles: list[Obstacle]       = []
tunnels:   list[TunnelObstacle] = []
coins:     list[Coin]           = []
tiles:     list[GroundTile]     = []
player:    Player | None        = None


# ── Spawn ─────────────────────────────────────────────────────────────

def _spawn_obstacle():
    kind = random.choices(
        ['barrier', 'train', 'overhead', 'tunnel'],
        weights=[4, 3, 2, 1]
    )[0]
    if kind == 'tunnel':
        tunnels.append(TunnelObstacle())
    else:
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
    # ── Rampen-Zug: Spieler landet auf dem Dach ───────────────────────
    # Nur wenn Spieler fällt (vel_y <= 0) und in richtiger Höhe
    if player.is_jumping and player.vel_y <= 0:
        phw, phh = player.half_extents()
        player_bottom = player.y - phh
        for o in obstacles:
            if o._dead or not o.has_ramp:
                continue
            if abs(o.x - player.x) >= o.hw + phw - 0.05:
                continue
            if abs(o.z - player.z) >= o.hz + 0.4:
                continue
            # Spieler-Boden nahe am Zugdach
            if player_bottom <= TRAIN_TOP + 0.2 and player_bottom >= TRAIN_TOP - 0.5:
                player.y          = TRAIN_TOP + phh
                player.vel_y      = 0.0
                player.is_jumping = False
                player.platform   = o
                break

    # ── Körper-Kollision mit Hindernissen ─────────────────────────────
    if not GS.is_invincible():
        hit = False
        for o in obstacles:
            if o._dead:
                continue
            # Rampen-Zug: kein Schaden bis der Spieler komplett drüber ist
            # Solange die Vorderkante des Zuges noch nicht weit hinter dem Spieler ist
            # und der Spieler in der gleichen Spur → Rampe wird gefahren, kein Schaden
            if o.has_ramp and abs(o.x - player.x) < o.hw + 0.5:
                train_front = o.z - o.hz
                if train_front > -3.0:   # Zug noch nicht komplett passiert
                    continue
            if o.hits_body(player):
                hit = True
                break
        if not hit:
            hit = any(not t._dead and t.hits_body(player) for t in tunnels)
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

    # ── Tote Entities entfernen ───────────────────────────────────────
    obstacles[:] = [o for o in obstacles if not o._dead]
    tunnels[:]   = [t for t in tunnels   if not t._dead]
    coins[:]     = [c for c in coins     if not c._dead]


# ── Game Over / Neustart ──────────────────────────────────────────────

def _show_game_over():
    hud_over.text    = 'GAME OVER'
    hud_sub.text     = f'Score: {GS.score}   Münzen: {GS.coins}'
    hud_restart.text = 'R  –  Neustart'
    hud_hint.enabled = False


def _reset():
    global obstacles, tunnels, coins, tiles, player

    for o in obstacles:
        for d in o._deco: destroy(d)
        destroy(o)
    for t in tunnels:
        for w in t._walls: destroy(w)
    for c in coins:  destroy(c)
    for ti in tiles: destroy(ti)
    if player: destroy(player)

    obstacles.clear(); tunnels.clear(); coins.clear(); tiles.clear()

    GS.reset()
    update_hearts(hearts, MAX_LIVES)
    hud_over.text = ''; hud_sub.text = ''; hud_restart.text = ''
    hud_hint.enabled = True

    player = Player()
    player.obstacles_ref = obstacles   # Referenz für Wandkollision

    for i in range(TILE_COUNT):
        tiles.append(GroundTile(i * TILE_LEN - TILE_LEN))


# ── Haupt-Update ──────────────────────────────────────────────────────

def update():
    if not GS.running:
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

    for t in tunnels:
        t.update()

    GS.obs_timer += dt
    if GS.obs_timer >= GS.obs_interval():
        _spawn_obstacle()
        GS.obs_timer = 0

    GS.coin_timer += dt
    if GS.coin_timer >= 1.2:
        _spawn_coins()
        GS.coin_timer = 0

    _check_collisions()


# ── Eingabe ───────────────────────────────────────────────────────────

def input(key):
    if not GS.running:
        if key == 'r': _reset()
        return
    if key in ('left arrow',  'a'):        player.action_left()
    if key in ('right arrow', 'd'):        player.action_right()
    if key in ('up arrow', 'w', 'space'):  player.action_jump()
    if key in ('down arrow',  's'):        player.action_slide()
    if key == 'escape':                    sys.exit()


# ── Szene aufbauen ────────────────────────────────────────────────────

camera.position   = (0, 4.5, -13)
camera.rotation_x = 16

DirectionalLight(direction=(1, -2, 1), color=color.white)
AmbientLight(color=C_AMBIENT)

make_buildings()
_reset()
app.run()

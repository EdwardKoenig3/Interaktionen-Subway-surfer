"""
Subway Surfer – 3D Prototype (Koop in einem Bildschirm)
Einstiegspunkt: python subway_surfer.py

Beide Spieler laufen gemeinsam in EINER Ansicht auf demselben Track. Sie sind an
ihrer Signalfarbe unterscheidbar (Spieler 1 cyan, Spieler 2 orange – Leucht-Marker
über dem Kopf, Boden-Ring und farbiges HUD) und durch einen kleinen seitlichen
Versatz. Leben und Punkte sind pro Spieler getrennt, Münzen werden geteilt
(wer zuerst dran ist, sammelt sie ein).

Dateistruktur:
    constants.py    – Farben und Spielkonstanten
    game_state.py   – GS (geteilter Track) + PlayerState (pro Spieler)
    player.py       – Player (Physik, Steuerung, Pushback, Marker)
    obstacles.py    – Obstacle (Auto, Zug, Overhead) – geteilt
    coins.py        – Coin – geteilt
    world.py        – GroundTile, make_buildings – geteilt
    hud.py          – PlayerHud (pro Spieler)
    menu.py         – StartMenu (1/2 Spieler, Steuerquelle)
    osc_input.py    – OSC (/game/vision/*, /game/voice/*)
    subway_surfer.py– App, Spawn, Kollision, Update, Input

Steuerung wird beim Start gewählt:
    TASTATUR  – Spieler 1 A/D/W/S, Spieler 2 Pfeiltasten (Einzelspieler: beides)
    VISION    – OSC /game/vision/{left,center,right,jump,slide,stand}
    VOICE     – OSC /game/voice/{left,center,right,jump,slide,stand}
"""

import random, sys, math
from ursina import *
from osc_input import start_osc_server, poll_actions, clear_actions, poll_pause

from constants import (
    C_SKY, C_AMBIENT,
    LANES, LANE_COUNT, SPAWN_Z, DESPAWN_Z,
    TILE_LEN, TILE_COUNT,
    SPEED_INC, JUMP_VEL, GRAVITY,
    PLAYER_BASE_Y, PLAYER_SY,
    TRAIN_TOP,
    MAX_LIVES, INVINCIBLE,
)
from game_state  import GS, PlayerState
from player      import Player
from obstacles   import Obstacle
from coins       import Coin
from world       import GroundTile, SidewalkTile, make_buildings
from hud         import PlayerHud
from menu        import StartMenu

# ── Kamera-Parameter ──────────────────────────────────────────────────
CAM_Y      = 6.0
CAM_ROT_X  = 18.0
CAM_Z_BASE = -18.0

# Signalfarben + seitlicher Versatz pro Spieler (in einem Bildschirm)
P1_COLOR  = color.cyan
P2_COLOR  = color.orange
P1_OFFSET = -0.42
P2_OFFSET = 0.42

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


# ── Pro-Spieler-Container ─────────────────────────────────────────────

class Side:
    """Alles, was zu einer Spielfigur gehört."""
    def __init__(self, state, player, hud, src, side):
        self.state  = state
        self.player = player
        self.hud    = hud
        self.src    = src      # 'keyboard' | 'vision' | 'voice'
        self.side   = side     # 'left' | 'right' | 'single'


# ── Globale Listen / Zustand ──────────────────────────────────────────
obstacles: list[Obstacle] = []
coins:     list[Coin]     = []
tiles:     list[GroundTile] = []
sides:     list[Side] = []
phase = 'menu'        # 'menu' | 'playing'
menu: StartMenu | None = None
restart_hint: Text | None = None
pause_text:   Text | None = None
result_text:  Text | None = None
result_sub:   Text | None = None


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


# ── Kollision (pro Spieler, geteilte Hindernisse + Münzen) ────────────

def _check_collisions(side: Side):
    if not side.state.alive:
        return
    player = side.player
    state  = side.state

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
    if not state.is_invincible():
        hit = False
        for o in obstacles:
            if o._dead:
                continue
            if o.has_ramp and abs(o.x - player.x) < o.hw + 0.5:
                train_front = o.z - o.hz
                in_ramp_zone = 0.3 <= train_front <= 3.3
                if player._ramp_jump or in_ramp_zone:
                    continue
            if o.hits_body(player):
                hit = True
                break
        if hit:
            state.lives    -= 1
            state.inv_timer = INVINCIBLE
            side.hud.update(state)
            if state.lives <= 0:
                state.alive = False
                _end_match_on_death(side)
                return
            # nur bei nicht-tödlichem Treffer: Wackeln + Zurückstoßen
            state.shake_t = 0.5
            player.pushback()

    # ── Münzen einsammeln (geteilt: wer zuerst dran ist) ──────────────
    for c in coins:
        if not c._dead and c.collect(player):
            c._dead = True
            state.coins += 1
            destroy(c)
            if state.coins % 50 == 0 and state.lives < MAX_LIVES:
                state.lives += 1
                side.hud.update(state)


# ── Game Over / Menü ──────────────────────────────────────────────────

def _end_match_on_death(dead_side: Side):
    """Sobald ein Spieler stirbt, endet das Match. In 2P gewinnt der andere."""
    GS.running = False
    if len(sides) == 2:
        winner = next((s for s in sides if s is not dead_side), None)
        wname  = 'SPIELER 1' if winner.side == 'left' else 'SPIELER 2'
        wcol   = P1_COLOR if winner.side == 'left' else P2_COLOR
        result_text.text  = f'{wname} GEWINNT!'
        result_text.color = wcol
        result_sub.text   = f'P1: {sides[0].state.score}   P2: {sides[1].state.score}'
    else:
        result_text.text  = 'GAME OVER'
        result_text.color = color.red
        result_sub.text   = f'Score: {dead_side.state.score}   Münzen: {dead_side.state.coins}'
    result_text.enabled  = True
    result_sub.enabled   = True
    restart_hint.text    = 'R  –  zurück zum Menü'
    restart_hint.enabled = True


def _hide_overlays():
    for t in (result_text, result_sub, pause_text):
        if t:
            t.text    = ''
            t.enabled = False
    if restart_hint:
        restart_hint.enabled = False


def _set_paused(p: bool):
    GS.paused = p
    if pause_text:
        pause_text.text    = 'PAUSE' if p else ''
        pause_text.enabled = p


def _teardown_match():
    for o in obstacles:
        for d in o._deco:
            destroy(d)
        destroy(o)
    obstacles.clear()
    for c in coins:
        destroy(c)
    coins.clear()
    for side in sides:
        destroy(side.player)
        side.hud.destroy()
    sides.clear()
    if restart_hint:
        restart_hint.enabled = False


def _start_match(cfg: dict):
    global phase
    _teardown_match()

    GS.reset()
    GS.running = True
    GS.paused  = False
    clear_actions()
    _hide_overlays()

    camera.position   = (0, CAM_Y, CAM_Z_BASE)
    camera.rotation_x = CAM_ROT_X

    if cfg['mode'] == 2:
        st_l = PlayerState()
        pl_l = Player(st_l, x_offset=P1_OFFSET, marker_color=P1_COLOR)
        pl_l.obstacles_ref = obstacles
        sides.append(Side(st_l, pl_l,
                          PlayerHud(x_center=-0.55, x_scale=0.6, accent=P1_COLOR, label='P1'),
                          src=cfg['sources'][0], side='left'))
        st_r = PlayerState()
        pl_r = Player(st_r, x_offset=P2_OFFSET, marker_color=P2_COLOR)
        pl_r.obstacles_ref = obstacles
        sides.append(Side(st_r, pl_r,
                          PlayerHud(x_center=0.55, x_scale=0.6, accent=P2_COLOR, label='P2'),
                          src=cfg['sources'][1], side='right'))
    else:
        st = PlayerState()
        pl = Player(st, x_offset=0.0, marker_color=None)
        pl.obstacles_ref = obstacles
        sides.append(Side(st, pl, PlayerHud(x_center=0.0, x_scale=1.0),
                          src=cfg['sources'][0], side='single'))

    for side in sides:
        side.hud.update(side.state)

    menu.set_visible(False)
    phase = 'playing'


def _to_menu():
    global phase
    _teardown_match()
    _hide_overlays()
    GS.running = False
    GS.paused  = True
    phase = 'menu'
    menu.set_visible(True)


# ── Haupt-Update ──────────────────────────────────────────────────────

def update():
    if phase != 'playing':
        return
    # OSC-Pause (Vision/Voice) – muss auch im pausierten Zustand greifen
    if GS.running and poll_pause():
        _set_paused(not GS.paused)
    if GS.paused:
        return
    dt = time.dt

    # ── geteilter Track ───────────────────────────────────────────────
    if GS.running:
        GS.elapsed += dt
        GS.speed   += SPEED_INC
        GS.obs_timer += dt
        if GS.obs_timer >= GS.obs_interval():
            _spawn_obstacle()
            GS.obs_timer = 0
        GS.coin_timer += dt
        if GS.coin_timer >= 1.2:
            _spawn_coins()
            GS.coin_timer = 0

    # ── pro Spieler ───────────────────────────────────────────────────
    for side in sides:
        st = side.state
        if st.alive:
            st.score = int(GS.elapsed * GS.speed * 2)
            if st.inv_timer > 0: st.inv_timer = max(0.0, st.inv_timer - dt)
            if st.shake_t  > 0: st.shake_t   = max(0.0, st.shake_t   - dt)
            if side.src in ('vision', 'voice'):
                poll_actions(side.player, side.src)
        _check_collisions(side)
        side.hud.update(st)

    # ── Kamera: Mittelwert der (lebenden) Spieler folgen + Shake ──────
    follow = [s for s in sides if s.state.alive] or sides
    avg_x  = sum(s.player.x for s in follow) / len(follow)
    avg_z  = sum(s.player.z for s in follow) / len(follow)
    cam_x  = avg_x * 0.25
    shake  = max((s.state.shake_t for s in sides), default=0.0)
    if shake > 0:
        cam_x += random.uniform(-0.45, 0.45) * (shake / 0.5)
    camera.x = lerp(camera.x, cam_x, min(7 * dt, 1))
    camera.z = lerp(camera.z, CAM_Z_BASE + avg_z * 0.35, min(10 * dt, 1))

    # ── tote Entities entfernen (geteilt) ─────────────────────────────
    obstacles[:] = [o for o in obstacles if not o._dead]
    coins[:]     = [c for c in coins     if not c._dead]


# ── Eingabe ───────────────────────────────────────────────────────────

def _handle_keyboard(side: Side, key):
    p = side.player
    if side.side == 'right':           # nur Pfeiltasten
        if   key == 'left arrow':       p.action_left()
        elif key == 'right arrow':      p.action_right()
        elif key == 'up arrow':         p.action_jump()
        elif key == 'down arrow':       p.start_slide()
        elif key == 'down arrow up':    p.stop_slide()
    elif side.side == 'left':          # nur WASD
        if   key == 'a':                p.action_left()
        elif key == 'd':                p.action_right()
        elif key in ('w', 'space'):     p.action_jump()
        elif key == 's':                p.start_slide()
        elif key == 's up':             p.stop_slide()
    else:                              # Einzelspieler: WASD UND Pfeiltasten
        if   key in ('a', 'left arrow'):            p.action_left()
        elif key in ('d', 'right arrow'):           p.action_right()
        elif key in ('w', 'up arrow', 'space'):     p.action_jump()
        elif key in ('s', 'down arrow'):            p.start_slide()
        elif key in ('s up', 'down arrow up'):      p.stop_slide()


def input(key):
    if key == 'escape':
        sys.exit()

    if phase == 'menu':
        if menu.handle_key(key) == 'start':
            _start_match(menu.config())
        return

    # phase == 'playing'
    if not GS.running:                 # alle tot → Game Over
        if key == 'r':
            _to_menu()
        return
    if key == 'p':
        _set_paused(not GS.paused)
        return
    if GS.paused:
        return
    for side in sides:
        if side.src == 'keyboard' and side.state.alive:
            _handle_keyboard(side, key)


# ── Szene aufbauen ────────────────────────────────────────────────────

camera.position   = (0, CAM_Y, CAM_Z_BASE)
camera.rotation_x = CAM_ROT_X

DirectionalLight(direction=(1, -2, 1), color=color.white)
AmbientLight(color=C_AMBIENT)

make_buildings()

# Geteilte Bodenkacheln (recyceln sich, einmal erzeugen)
for i in range(TILE_COUNT):
    z = i * TILE_LEN - TILE_LEN
    tiles.append(GroundTile(z))
    tiles.append(SidewalkTile(z, -1))
    tiles.append(SidewalkTile(z, +1))

restart_hint = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.42),
                    scale=1.3, color=color.white, z=0)
restart_hint.enabled = False

pause_text = Text('', parent=camera.ui, origin=(0, 0), position=(0, 0.0),
                  scale=2.6, color=color.white, z=0)
pause_text.enabled = False
result_text = Text('', parent=camera.ui, origin=(0, 0), position=(0, 0.06),
                   scale=3.0, color=color.yellow, z=0)
result_text.enabled = False
result_sub = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.06),
                  scale=1.4, color=color.white, z=0)
result_sub.enabled = False

GS.running = False
GS.paused  = True
menu = StartMenu()
phase = 'menu'

start_osc_server()
app.run()

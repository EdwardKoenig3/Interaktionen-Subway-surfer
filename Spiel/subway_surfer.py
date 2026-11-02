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
    menu.py         – StartMenu (1/2 Spieler, Steuerquelle, Power-ups)
    powerups.py     – Power-ups (Schild, Gleiten, Magnet) mit Abklingzeit
    osc_input.py    – OSC (/game/vision/*, /game/vision2/*, /game/voice/*)
    subway_surfer.py– App, Spawn, Kollision, Update, Input

Steuerung wird beim Start gewählt:
    TASTATUR  – Spieler 1 A/D/W/S, Spieler 2 Pfeiltasten (Einzelspieler: beides)
                Power-ups: Q/E/F (Spieler 1) bzw. J/K/L (Spieler 2)
    VISION    – OSC /game/vision/{left,center,right,jump,slide,stand,power}
    VISION 2  – OSC /game/vision2/… (zweiter Spieler vor derselben Kamera)
    VOICE     – OSC /game/voice/{left,center,right,jump,slide,stand}

Meldet die Kamera /game/vision/lost 1 (Spieler nicht erkannt), hält das Spiel an,
bis er wieder vor der Kamera steht.

Manche Züge haben vorne eine Rampe – darüber läuft man ohne Sprung aufs Dach.
"""

import random, sys, math
from ursina import *
import time as pytime   # ursinas `time` (mit dt) bleibt unberührt
from osc_input import (start_osc_server, poll_actions, clear_actions, poll_pause,
                       poll_start, set_active_sources, player_lost, OSC_PORT)

from constants import (
    C_SKY, C_AMBIENT,
    LANES, LANE_COUNT, SPAWN_Z, SPAWN_GAP, DESPAWN_Z,
    OBS_SPACING, DOUBLE_SPAWN_CHANCE, TRAIN_WALL_MARGIN_S,
    TILE_LEN, TILE_COUNT,
    SPEED_INC, MAX_SPD, JUMP_VEL, GRAVITY,
    PLAYER_BASE_Y, PLAYER_SY,
    TRAIN_TOP, RAMP_CHANCE,
    INVINCIBLE, COIN_SCORE, COIN_CLEARANCE,
)
from powerups    import MAGNET_RANGE_Z
from game_state  import GS, PlayerState
from player      import Player
from obstacles   import Obstacle, TRAIN_LENGTHS
from coins       import Coin
from world       import GroundTile, SidewalkTile, make_buildings
from hud         import PlayerHud
from menu        import StartMenu
import leaderboard
from leaderboard import LeaderboardView, MAX_NAME_LEN

# ── Kamera-Parameter ──────────────────────────────────────────────────
# Flache Neigung → Spieler steht im unteren Bilddrittel, man sieht weiter voraus.
# (Ursina-FOV 40° ist horizontal → bei 16:9 nur ca. ±11,5° vertikal.)
CAM_Y      = 6.0
CAM_ROT_X  = 10.0     # vorher 18 (Spieler fast in Bildmitte)
CAM_Z_BASE = -18.0
# Wie stark die Kamera dem Spieler beim Zurückstoßen nach hinten folgt.
# Bei flacher Neigung muss sie mehr mitgehen, sonst rutscht er unten aus dem Bild.
CAM_FOLLOW_Z = 0.75   # vorher 0.35

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
# Himmelskugel muss größer sein als die Sichtweite (Straße bis z ≈ 330),
# sonst verdeckt sie die weit entfernten Häuser/Straße
Entity(model='sphere', texture='textures/sky.png', scale=1000,
       double_sided=True, unlit=True, eternal=True)


# ── Pro-Spieler-Container ─────────────────────────────────────────────

class Side:
    """Alles, was zu einer Spielfigur gehört."""
    def __init__(self, state, player, hud, src, side):
        self.state  = state
        self.player = player
        self.hud    = hud
        self.src    = src      # 'keyboard' | 'vision' | 'vision2' | 'voice'
        self.side   = side     # 'left' | 'right' | 'single'


# Steuerquellen, die per OSC kommen (Kamera-Spieler 1/2, Sprache)
OSC_SOURCES = ('vision', 'vision2', 'voice')

# Power-up-Tasten (Tastatur-Spieler): links/Einzelspieler Q/E/F, rechts J/K/L
_POWER_KEYS = {
    'left':  {'q': 'shield', 'e': 'glide', 'f': 'magnet'},
    'right': {'j': 'shield', 'k': 'glide', 'l': 'magnet'},
}
_POWER_KEYS['single'] = {**_POWER_KEYS['left'], **_POWER_KEYS['right']}


# ── Globale Listen / Zustand ──────────────────────────────────────────
obstacles: list[Obstacle] = []
coins:     list[Coin]     = []
tiles:     list[GroundTile] = []
sides:     list[Side] = []
phase = 'menu'        # 'menu' | 'playing'
menu: StartMenu | None = None
restart_hint: Text | None = None
pause_text:   Text | None = None
hold_text:    Text | None = None
hold_sub:     Text | None = None
result_text:  Text | None = None
result_sub:   Text | None = None

# GS.paused = manuelle Pause (P / OSC .../pause) ODER Tracking-Pause (die Kamera
# erkennt den Spieler gerade nicht, OSC .../lost) – beide getrennt merken
manual_pause  = False
tracking_hold = False

# Bestenliste nach Game Over (nur Einzelspieler)
gameover_board: LeaderboardView | None = None
name_prompt:  Text | None = None
name_line:    Text | None = None
# Läuft gerade eine Namenseingabe? {'src', 'score', 'coins', 'name'} oder None
name_entry:   dict | None = None

# Start-Geste (OSC /game/<quelle>/start): im Menü → Spiel starten,
# nach Game Over → zurück ins Menü (frühestens GESTURE_GAMEOVER_DELAY s danach)
GESTURE_GAMEOVER_DELAY = 2.0
gameover_at = 0.0
MENU_HINT_GAMEOVER = 'R  oder  beide Arme hoch  –  zurück zum Menü'


# ── Spawn ─────────────────────────────────────────────────────────────

def _lane_free_for_spawn(lane: int) -> bool:
    """Spur ist frei, wenn kein Hindernis mehr in den Spawn-Bereich hineinragt.
    Verhindert, dass ein neues Hindernis in einem noch nicht vorbeigefahrenen
    (langen) Zug entsteht."""
    for o in obstacles:
        if not o._dead and o.lane == lane and o.z + o.hz > SPAWN_Z - SPAWN_GAP:
            return False
    return True


# "Beutel" mit Spuren: jede Spur kommt pro 3er-Runde genau einmal dran, nur die
# Reihenfolge ist zufällig → nie lange Serien auf derselben Spur.
_lane_bag: list[int] = []

_KINDS   = ['car', 'train', 'train_long', 'train_xl', 'overhead']
_WEIGHTS = [3, 6, 3, 1, 2]


def _draw_lane(exclude: set[int]) -> int | None:
    """Nächste freie Spur aus dem Beutel. Belegte Spuren bleiben für später drin.
    Passt keine Spur aus dem Beutel, wird irgendeine freie genommen."""
    if not _lane_bag:
        _lane_bag.extend(random.sample(range(LANE_COUNT), LANE_COUNT))
    for lane in _lane_bag:
        if lane not in exclude and _lane_free_for_spawn(lane):
            _lane_bag.remove(lane)
            return lane
    free = [l for l in range(LANE_COUNT) if l not in exclude and _lane_free_for_spawn(l)]
    return random.choice(free) if free else None


def _train_would_block(lane: int, length: float) -> bool:
    """True, wenn ein neuer Zug in `lane` zusammen mit Zügen in den beiden anderen
    Spuren alle Spuren versperren würde. Geprüft wird die Zuglänge plus
    ± (Tempo × TRAIN_WALL_MARGIN_S), damit auch der Wechsel dorthin noch klappt."""
    margin = GS.speed * TRAIN_WALL_MARGIN_S
    lo, hi = SPAWN_Z - margin, SPAWN_Z + length + margin
    blocked = {o.lane for o in obstacles
               if not o._dead and o.kind == 'train' and o.lane != lane
               and o.z - o.hz < hi and o.z + o.hz > lo}
    return len(blocked) >= LANE_COUNT - 1


def _pick_kind(lane: int) -> str:
    kind = random.choices(_KINDS, weights=_WEIGHTS)[0]
    # Würde der Zug die letzte freie Spur dichtmachen → Auto oder Balken stattdessen
    if kind.startswith('train') and _train_would_block(lane, TRAIN_LENGTHS[kind][1]):
        kind = random.choice(['car', 'overhead'])
    return kind


def _spawn_obstacle() -> bool:
    """Spawnt ein Hindernis (mit DOUBLE_SPAWN_CHANCE zwei nebeneinander).
    False, wenn gerade keine Spur frei ist."""
    count = 2 if random.random() < DOUBLE_SPAWN_CHANCE else 1
    used: set[int] = set()
    for _ in range(count):
        lane = _draw_lane(used)
        if lane is None:
            break
        kind = _pick_kind(lane)
        ramp = kind.startswith('train') and random.random() < RAMP_CHANCE
        o = Obstacle(lane, kind, ramp=ramp)
        obstacles.append(o)
        _remove_coins_inside(o)
        if ramp and random.random() < 0.7:
            _spawn_ramp_coins(o)
        used.add(lane)
    return bool(used)


# ── Münzen ────────────────────────────────────────────────────────────
# Münzen dürfen nicht IN einem Hindernis liegen (unerreichbar). ÜBER einem
# Hindernis sind sie erlaubt – z.B. ein Münzbogen über ein Auto.

def _inside_obstacle(o: Obstacle, lane: int, z: float, y: float) -> bool:
    if o._dead or o.lane != lane:
        return False
    return ((abs(o.z - z) < o.hz + COIN_CLEARANCE and abs(o.y - y) < o.hh + COIN_CLEARANCE)
            or o.ramp_contains(z, y, COIN_CLEARANCE))


def _spawn_ramp_coins(o: Obstacle):
    """Münzspur die Rampe hinauf und ein Stück übers Dach – zeigt den neuen Weg."""
    start = o.front_z - o.ramp_len
    spots = [start + (i + 0.5) * o.ramp_len / 4 for i in range(4)]
    spots += [o.front_z + 1.0 + i * 1.8 for i in range(min(5, int(o.hz * 2 / 1.8)))]
    for z in spots:
        surface = o.ramp_surface(z)
        y = (o.roof_y if surface is None else surface) + 0.5
        if not any(_inside_obstacle(p, o.lane, z, y) for p in obstacles if p is not o):
            coins.append(Coin(o.lane, z, y=y))


def _coin_blocked(lane: int, z: float, y: float) -> bool:
    return any(_inside_obstacle(o, lane, z, y) for o in obstacles)


def _remove_coins_inside(o: Obstacle):
    """Münzen entfernen, in denen ein gerade gespawntes Hindernis stecken würde.
    Nötig, weil lange Münzbögen bei hohem Tempo weit hinter den Spawnpunkt reichen."""
    for c in coins:
        if not c._dead and _inside_obstacle(o, c.lane, c.z, c.y):
            c._dead = True
            destroy(c)


def _coin_pattern() -> list[tuple[float, float]]:
    """(z, y)-Positionen einer zufälligen Münzgruppe."""
    mode = random.choices(['line', 'arc', 'high'], weights=[4, 4, 2])[0]
    if mode == 'arc':
        T = 2 * JUMP_VEL / abs(GRAVITY)
        n = 7
        pattern = []
        for i in range(n):
            t = T * i / (n - 1)
            y = PLAYER_BASE_Y + JUMP_VEL * t + 0.5 * GRAVITY * t ** 2
            pattern.append((SPAWN_Z + GS.speed * t, max(y, PLAYER_BASE_Y + 0.1)))
        return pattern
    if mode == 'high':
        return [(SPAWN_Z + i * 1.8, TRAIN_TOP + 0.45) for i in range(random.randint(3, 5))]
    return [(SPAWN_Z + i * 1.7, 1.0) for i in range(random.randint(3, 6))]


def _spawn_coins():
    """Münzgruppe in die Spur, in der am wenigsten Münzen in Hindernissen
    stecken würden (bei Gleichstand zufällig). Münzen, die trotzdem in einem
    Hindernis lägen, entfallen."""
    pattern = _coin_pattern()
    lanes = random.sample(range(LANE_COUNT), LANE_COUNT)
    lane = min(lanes, key=lambda l: sum(_coin_blocked(l, z, y) for z, y in pattern))
    for z, y in pattern:
        if not _coin_blocked(lane, z, y):
            coins.append(Coin(lane, z, y=y))


# ── Kollision (pro Spieler, geteilte Hindernisse + Münzen) ────────────

def _check_collisions(side: Side) -> bool:
    """Kollisionen eines Spielers prüfen. True, wenn er dabei gestorben ist."""
    if not side.state.alive:
        return False
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
            if not o.z_overlaps(player.z, 0.4):
                continue
            plat_top  = o.y + o.hh
            if plat_top - 0.5 <= player_bottom <= plat_top + 0.3:
                player.y          = plat_top + phh
                player.vel_y      = 0.0
                player.is_jumping = False
                player.platform   = o
                break

    # ── Körper-Kollision mit Hindernissen ─────────────────────────────
    if not state.is_invincible():
        hit = False
        for o in obstacles:
            # Auf der Rampe eines Zugs läuft man über ihn hinweg, nicht hinein
            if o._dead or o is player.ramp:
                continue
            if o.hits_body(player):
                hit = True
                break
        if hit and state.powers.is_active('shield'):
            # Schild fängt den Treffer ab: kein Leben weg, kurz unverwundbar
            # (lange genug, um durch das Hindernis hindurchzukommen)
            state.powers.end('shield')
            state.inv_timer = INVINCIBLE
            side.hud.notify('SCHILD HÄLT!', color.cyan)
        elif hit:
            state.lives    -= 1
            state.inv_timer = INVINCIBLE
            side.hud.update(state)
            if state.lives <= 0:
                state.alive = False
                return True
            # nur bei nicht-tödlichem Treffer: Wackeln + Zurückstoßen
            state.shake_t = 0.5
            player.pushback()

    # ── Münzen einsammeln (geteilt: wer zuerst dran ist) ──────────────
    for c in coins:
        if not c._dead and c.collect(player):
            c._dead = True
            state.coins += 1
            destroy(c)
    return False


def _pull_coins(player: Player, dt: float):
    """Magnet: Münzen voraus fliegen zum Spieler – genau so schnell, dass sie
    bei ihm ankommen, wenn sie seine Höhe (z) erreichen; dort sammelt er sie ein."""
    for c in coins:
        if c._dead:
            continue
        ahead = c.z - player.z
        if not -0.5 < ahead < MAGNET_RANGE_Z:
            continue
        t_left = max(ahead / max(GS.speed, 1e-3), dt)    # Zeit bis zum Spieler
        f = min(1.0, dt / t_left)
        c.x += (player.x - c.x) * f
        c.y += (player.y - c.y) * f


# ── Game Over / Menü ──────────────────────────────────────────────────

def _end_match(dead_sides: list[Side]):
    """Sobald ein Spieler stirbt, endet das Match. In 2P gewinnt der andere,
    sterben beide im selben Frame, ist es unentschieden.
    Im Einzelspieler folgt die Bestenliste (ggf. mit Namenseingabe)."""
    global name_entry, gameover_at
    GS.running = False
    gameover_at = pytime.monotonic()
    set_active_sources(())
    if len(sides) == 2:
        result_text.y, result_sub.y = 0.06, -0.06
        if len(dead_sides) >= 2:
            result_text.text  = 'UNENTSCHIEDEN'
            result_text.color = color.white
        else:
            winner = next(s for s in sides if s is not dead_sides[0])
            wname  = 'SPIELER 1' if winner.side == 'left' else 'SPIELER 2'
            wcol   = P1_COLOR if winner.side == 'left' else P2_COLOR
            result_text.text  = f'{wname} GEWINNT!'
            result_text.color = wcol
        result_sub.text = f'P1: {sides[0].state.score}   P2: {sides[1].state.score}'
    else:
        dead = dead_sides[0]
        result_text.y, result_sub.y = 0.36, 0.28   # oben Platz für die Bestenliste
        result_text.text  = 'GAME OVER'
        result_text.color = color.red
        result_sub.text   = f'Score: {dead.state.score}   Münzen: {dead.state.coins}'
        gameover_board.show(dead.src)
        if leaderboard.qualifies(dead.src, dead.state.score):
            name_entry = {'src': dead.src, 'score': dead.state.score,
                          'coins': dead.state.coins, 'name': ''}
            _update_name_prompt()
    result_text.enabled  = True
    result_sub.enabled   = True
    restart_hint.text    = ('Name tippen  –  ENTER speichern  –  ESC überspringen'
                            if name_entry else MENU_HINT_GAMEOVER)
    restart_hint.enabled = True


# ── Bestenliste: Namenseingabe ────────────────────────────────────────

def _update_name_prompt():
    name_prompt.text    = 'NEUER HIGHSCORE!  Dein Name:'
    name_line.text      = name_entry['name'] + '_'
    name_prompt.enabled = True
    name_line.enabled   = True


def _finish_name_entry(save: bool):
    global name_entry
    entry, name_entry = name_entry, None
    highlight = None
    if save:
        highlight = leaderboard.add_entry(entry['src'], entry['name'], entry['score'], entry['coins'])
    name_prompt.enabled = False
    name_line.enabled   = False
    gameover_board.show(entry['src'], highlight)
    restart_hint.text = MENU_HINT_GAMEOVER


def _handle_name_key(key: str):
    if ' ' in key:                     # 'a up', 'a hold' … ignorieren
        return
    name = name_entry['name']
    if key == 'enter':
        _finish_name_entry(save=True)
        return
    if key == 'escape':
        _finish_name_entry(save=False)
        return
    if key == 'backspace':
        name = name[:-1]
    elif len(name) < MAX_NAME_LEN:
        if key == 'space' and name:
            name += ' '
        elif len(key) == 1 and (key.isalnum() or key in '-_'):
            name += key.upper()
    name_entry['name'] = name
    _update_name_prompt()


def _hide_overlays():
    global name_entry
    name_entry = None
    for t in (result_text, result_sub, pause_text, name_prompt, name_line):
        if t:
            t.text    = ''
            t.enabled = False
    for t in (hold_text, hold_sub):   # feste Texte, nur ausblenden
        if t:
            t.enabled = False
    if restart_hint:
        restart_hint.enabled = False
    if gameover_board:
        gameover_board.hide()


def _osc_sources() -> set[str]:
    return {s.src for s in sides if s.src in OSC_SOURCES}


def _apply_pause():
    GS.paused = manual_pause or tracking_hold
    # In der Pause eintreffende Gesten/Sprachbefehle verwerfen statt puffern
    set_active_sources(() if GS.paused else _osc_sources())
    if pause_text:
        pause_text.text    = 'PAUSE' if manual_pause else ''
        pause_text.enabled = manual_pause
    for t in (hold_text, hold_sub):
        if t:
            t.enabled = tracking_hold and not manual_pause


def _set_paused(p: bool):
    global manual_pause
    manual_pause = p
    _apply_pause()


def _set_tracking_hold(hold: bool):
    """Kamera erkennt den Spieler nicht → anhalten, bis er wieder da ist."""
    global tracking_hold
    if hold != tracking_hold:
        tracking_hold = hold
        _apply_pause()


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
    global phase, manual_pause, tracking_hold
    _teardown_match()

    GS.reset()
    GS.running  = True
    GS.paused   = False
    GS.powerups = cfg.get('powerups', True)
    manual_pause = tracking_hold = False
    _lane_bag.clear()
    clear_actions()
    _hide_overlays()

    camera.position   = (0, CAM_Y, CAM_Z_BASE)
    camera.rotation_x = CAM_ROT_X

    pw = GS.powerups
    if cfg['mode'] == 2:
        st_l = PlayerState()
        pl_l = Player(st_l, x_offset=P1_OFFSET, marker_color=P1_COLOR)
        pl_l.obstacles_ref = obstacles
        sides.append(Side(st_l, pl_l,
                          PlayerHud(x_center=-0.55, x_scale=0.6, accent=P1_COLOR, label='P1', powerups=pw),
                          src=cfg['sources'][0], side='left'))
        st_r = PlayerState()
        pl_r = Player(st_r, x_offset=P2_OFFSET, marker_color=P2_COLOR)
        pl_r.obstacles_ref = obstacles
        sides.append(Side(st_r, pl_r,
                          PlayerHud(x_center=0.55, x_scale=0.6, accent=P2_COLOR, label='P2', powerups=pw),
                          src=cfg['sources'][1], side='right'))
    else:
        st = PlayerState()
        pl = Player(st, x_offset=0.0, marker_color=None)
        pl.obstacles_ref = obstacles
        sides.append(Side(st, pl, PlayerHud(x_center=0.0, x_scale=1.0, powerups=pw),
                          src=cfg['sources'][0], side='single'))

    for side in sides:
        side.hud.update(side.state)

    set_active_sources(_osc_sources())
    menu.set_visible(False)
    phase = 'playing'


def _to_menu():
    global phase, manual_pause, tracking_hold
    _teardown_match()
    _hide_overlays()
    GS.running = False
    GS.paused  = True
    manual_pause = tracking_hold = False
    set_active_sources(())
    phase = 'menu'
    menu.set_visible(True)


# ── Haupt-Update ──────────────────────────────────────────────────────

def _handle_start_gesture(sources: set[str]):
    """Start-Geste auswerten. Im laufenden Spiel und während der Namenseingabe
    wird sie ignoriert (die Queue wird trotzdem geleert, damit nichts nachwirkt)."""
    if phase == 'menu':
        cfg = menu.config()
        # Nur starten, wenn die Geste von einer gewählten Quelle kommt –
        # sonst könnte ein Zuschauer vor der Kamera eine Tastatur-Runde starten
        if sources & set(cfg['sources']):
            _start_match(cfg)
    elif not GS.running and name_entry is None:
        if pytime.monotonic() - gameover_at >= GESTURE_GAMEOVER_DELAY:
            _to_menu()


def update():
    starts = poll_start()
    if starts:
        _handle_start_gesture(starts)
    if phase != 'playing':
        return
    # OSC-Pause (Vision/Voice) – muss auch im pausierten Zustand greifen
    if GS.running and poll_pause():
        _set_paused(not manual_pause)
    # Kamera erkennt den Spieler gerade nicht (OSC .../lost) → warten, bis er
    # wieder vor der Kamera steht, statt ihn ungesteuert weiterlaufen zu lassen
    if GS.running:
        _set_tracking_hold(player_lost(_osc_sources()))
    if GS.paused:
        return
    dt = time.dt

    if GS.running:
        # ── geteilter Track ───────────────────────────────────────────
        GS.elapsed += dt
        # pro Sekunde → unabhängig von der Bildrate; gedeckelt bei MAX_SPD
        GS.speed    = min(MAX_SPD, GS.speed + SPEED_INC * dt)
        # Spawn nach zurückgelegter Strecke, nicht nach Zeit → der physische
        # Abstand zwischen Hindernissen bleibt bei jedem Tempo gleich.
        # Ist gerade keine Spur frei, wird im nächsten Frame erneut versucht.
        GS.obs_dist += GS.speed * dt
        if GS.obs_dist >= OBS_SPACING and _spawn_obstacle():
            GS.obs_dist = 0.0
        GS.coin_timer += dt
        if GS.coin_timer >= 1.2:
            _spawn_coins()
            GS.coin_timer = 0

        # ── pro Spieler ───────────────────────────────────────────────
        # Erst alle Spieler prüfen, dann das Match beenden – so wird ein
        # gleichzeitiger Tod beider Spieler als Unentschieden erkannt.
        died = []
        for side in sides:
            st = side.state
            if st.alive:
                st.score = int(GS.elapsed * GS.speed * 2) + st.coins * COIN_SCORE
                if st.inv_timer > 0: st.inv_timer = max(0.0, st.inv_timer - dt)
                if st.shake_t  > 0: st.shake_t   = max(0.0, st.shake_t   - dt)
                st.powers.update(dt)
                if side.src in OSC_SOURCES:
                    for name, ok in poll_actions(side.player, side.src):
                        side.hud.notify_power(name, ok, st)
                if st.powers.is_active('magnet'):
                    _pull_coins(side.player, dt)
            if _check_collisions(side):
                died.append(side)
            side.hud.update(st)
        if died:
            _end_match(died)

    # ── Kamera: Mittelwert der (lebenden) Spieler folgen + Shake ──────
    follow = [s for s in sides if s.state.alive] or sides
    avg_x  = sum(s.player.x for s in follow) / len(follow)
    avg_z  = sum(s.player.z for s in follow) / len(follow)
    cam_x  = avg_x * 0.25
    # Nach Match-Ende laufen die Shake-Timer nicht mehr ab → kein Wackeln mehr
    shake  = max((s.state.shake_t for s in sides), default=0.0) if GS.running else 0.0
    if shake > 0:
        cam_x += random.uniform(-0.45, 0.45) * (shake / 0.5)
    camera.x = lerp(camera.x, cam_x, min(7 * dt, 1))
    camera.z = lerp(camera.z, CAM_Z_BASE + avg_z * CAM_FOLLOW_Z, min(10 * dt, 1))

    # ── tote Entities entfernen (geteilt) ─────────────────────────────
    obstacles[:] = [o for o in obstacles if not o._dead]
    coins[:]     = [c for c in coins     if not c._dead]


# ── Eingabe ───────────────────────────────────────────────────────────

def _handle_keyboard(side: Side, key):
    p = side.player
    power = _POWER_KEYS[side.side].get(key)
    if power is not None:
        if GS.powerups:
            side.hud.notify_power(power, p.activate_power(power), side.state)
        return
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
    # Während der Namenseingabe gehen alle Tasten (auch R, P, ESC) an das Namensfeld
    if name_entry is not None:
        _handle_name_key(key)
        return

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
        _set_paused(not manual_pause)
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
    z = DESPAWN_Z + (i + 0.5) * TILE_LEN     # lückenlos von DESPAWN_Z bis ca. z = 330
    tiles.append(GroundTile(z))
    tiles.append(SidewalkTile(z, -1))
    tiles.append(SidewalkTile(z, +1))

restart_hint = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.42),
                    scale=1.3, color=color.white, z=0)
restart_hint.enabled = False

pause_text = Text('', parent=camera.ui, origin=(0, 0), position=(0, 0.0),
                  scale=2.6, color=color.white, z=0)
pause_text.enabled = False
hold_text = Text('SPIELER NICHT ERKANNT', parent=camera.ui, origin=(0, 0), position=(0, 0.05),
                 scale=2.4, color=color.orange, z=0)
hold_text.enabled = False
hold_sub = Text('Zurück vor die Kamera stellen – dann geht es weiter', parent=camera.ui,
                origin=(0, 0), position=(0, -0.05), scale=1.3, color=color.white, z=0)
hold_sub.enabled = False
result_text = Text('', parent=camera.ui, origin=(0, 0), position=(0, 0.06),
                   scale=3.0, color=color.yellow, z=0)
result_text.enabled = False
result_sub = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.06),
                  scale=1.4, color=color.white, z=0)
result_sub.enabled = False

gameover_board = LeaderboardView(x_center=0.0, y_top=0.20)
name_prompt = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.24),
                   scale=1.3, color=color.yellow, z=0)
name_prompt.enabled = False
name_line = Text('', parent=camera.ui, origin=(0, 0), position=(0, -0.31),
                 scale=2.0, color=color.white, z=0)
name_line.enabled = False

GS.running = False
GS.paused  = True
menu = StartMenu()
phase = 'menu'

if not start_osc_server():
    # Ohne OSC funktionieren VISION/VOICE nicht – dauerhaft sichtbar warnen
    Text(f'OSC nicht verfügbar (Port {OSC_PORT}) – nur Tastatur möglich. Details in der Konsole.',
         parent=camera.ui, origin=(0, 0), position=(0, -0.47),
         scale=1.0, color=color.red, z=-1, eternal=True)
app.run()

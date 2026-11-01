"""
osc_input.py  –  OSC-Empfänger für Subway Surfer (Multiplayer).

Zwei getrennte Namespaces, damit zwei Spieler unabhängig gesteuert werden:

    Spieler „vision"                 Spieler „voice"
    /game/vision/left                /game/voice/left
    /game/vision/center              /game/voice/center
    /game/vision/right               /game/voice/right
    /game/vision/jump                /game/voice/jump
    /game/vision/slide               /game/voice/slide
    /game/vision/stand               /game/voice/stand

Die alten Adressen ohne Präfix (/game/left, /game/jump, …) werden weiterhin auf
den Vision-Spieler gemappt (Rückwärtskompatibilität für bestehende Sender).

Beispiel-Sender (gleicher Rechner → "127.0.0.1", sonst IP des Spiel-Rechners):
    from pythonosc.udp_client import SimpleUDPClient
    client = SimpleUDPClient("127.0.0.1", 9000)
    client.send_message("/game/vision/center", [])
    client.send_message("/game/voice/jump", [])

Der Port kommt aus network.json im Projekt-Root (Standard 9000).
"""

import json
import queue
import threading
from pathlib import Path

try:
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer
    _OSC_AVAILABLE = True
except ImportError:
    _OSC_AVAILABLE = False

_NETWORK_FILE = Path(__file__).resolve().parent.parent / "network.json"


def _load_port(default: int = 9000) -> int:
    try:
        return int(json.loads(_NETWORK_FILE.read_text(encoding="utf-8")).get("port", default))
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, ValueError, OSError) as e:
        print(f"[OSC] {_NETWORK_FILE.name} fehlerhaft ({e}) – nutze Port {default}")
        return default


# 0.0.0.0 = auf allen Interfaces lauschen: empfängt sowohl lokal (127.0.0.1)
# als auch von anderen Rechnern im Netz
OSC_IP   = "0.0.0.0"
OSC_PORT = _load_port()

# Eine Queue pro Steuerquelle
_queues: dict[str, queue.Queue] = {
    "vision": queue.Queue(),
    "voice":  queue.Queue(),
}

# Pause ist global (quellenunabhängig) → eigene Queue
_pause_q: queue.Queue = queue.Queue()

# Start-Geste (Menü → Spiel, Game Over → Menü). Enthält die Quelle ('vision'/'voice').
# Wird immer angenommen; ob sie gerade etwas bewirkt, entscheidet das Spiel.
_start_q: queue.Queue = queue.Queue()

# Nur Aktionen dieser Quellen werden angenommen. Alles andere (Menü, Pause,
# Game Over, nicht gewählte Quelle) wird beim Empfang verworfen – sonst laufen
# die Queues voll und alte Befehle werden später auf einmal ausgeführt.
_active_sources: frozenset[str] = frozenset()


def set_active_sources(sources) -> None:
    """Legt fest, welche Quellen ('vision', 'voice') gerade Aktionen liefern dürfen."""
    global _active_sources
    _active_sources = frozenset(sources)


def start_osc_server() -> bool:
    if not _OSC_AVAILABLE:
        print("[OSC] pythonosc nicht installiert – pip install python-osc")
        return False

    dispatcher = Dispatcher()

    def _log(addr, *args):
        print(f"[OSC] {addr}  {list(args)}")

    def _lane(source, n):
        def _h(addr, *args):
            _log(addr, *args)
            if source in _active_sources:
                _queues[source].put(("lane", n))
        return _h

    def _action(source, name):
        def _h(addr, *args):
            _log(addr, *args)
            if source in _active_sources:
                _queues[source].put(("action", name))
        return _h

    def _pause_handler(addr, *args):
        _log(addr, *args)
        _pause_q.put(1)

    def _start(source):
        def _h(addr, *args):
            _log(addr, *args)
            _start_q.put(source)
        return _h

    def _map_namespace(prefix, source):
        dispatcher.map(f"{prefix}/left",   _lane(source, 0))
        dispatcher.map(f"{prefix}/center", _lane(source, 1))
        dispatcher.map(f"{prefix}/right",  _lane(source, 2))
        dispatcher.map(f"{prefix}/jump",   _action(source, "jump"))
        dispatcher.map(f"{prefix}/slide",  _action(source, "slide"))
        dispatcher.map(f"{prefix}/stand",  _action(source, "stand"))
        dispatcher.map(f"{prefix}/pause",  _pause_handler)
        dispatcher.map(f"{prefix}/start",  _start(source))

    _map_namespace("/game/vision", "vision")
    _map_namespace("/game/voice",  "voice")
    _map_namespace("/game",        "vision")   # Rückwärtskompatibilität
    dispatcher.set_default_handler(lambda addr, *a: print(f"[OSC] (unbekannt) {addr}  {list(a)}"))

    try:
        server = ThreadingOSCUDPServer((OSC_IP, OSC_PORT), dispatcher)
    except OSError as e:
        print(f"[OSC] Konnte Server nicht starten: {e}")
        return False

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[OSC] Server läuft auf {OSC_IP}:{OSC_PORT}")
    print("[OSC] Vision: /game/vision/{left,center,right,jump,slide,stand,pause,start}")
    print("[OSC] Voice:  /game/voice/{left,center,right,jump,slide,stand,pause,start}")
    return True


def clear_actions() -> None:
    """Alle gepufferten OSC-Aktionen (inkl. Pause) verwerfen (z. B. beim Match-Start)."""
    for q in (*_queues.values(), _pause_q):
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break


def poll_pause() -> bool:
    """True, wenn seit dem letzten Aufruf mindestens ein Pause-Event eintraf."""
    got = False
    while not _pause_q.empty():
        try:
            _pause_q.get_nowait()
            got = True
        except queue.Empty:
            break
    return got


def poll_start() -> set[str]:
    """Quellen, von denen seit dem letzten Aufruf eine Start-Geste kam (leert die Queue)."""
    sources = set()
    while not _start_q.empty():
        try:
            sources.add(_start_q.get_nowait())
        except queue.Empty:
            break
    return sources


def poll_actions(player, source: str) -> None:
    """OSC-Aktionen der angegebenen Quelle auf den Spieler anwenden.

    `source` ist "vision" oder "voice". Slide und Sprung sind zeit-/impulsbasiert
    und laufen vollständig durch – eine reale Geste ist kürzer als die in-Game-
    Animation, deshalb bricht "stand" sie NICHT ab. Ausnahmen (siehe Player):
    ein Sprung beendet ein laufendes Ducken, Ducken in der Luft lässt die Figur
    schnell fallen. Spuren werden gemerkt, falls der Weg gerade blockiert ist.
    """
    q = _queues.get(source)
    if q is None:
        return
    while not q.empty():
        try:
            msg = q.get_nowait()
        except queue.Empty:
            break
        kind = msg[0]
        if kind == "lane":
            # Slide NICHT abbrechen – Spieler darf während Slide die Spur wechseln.
            player.set_lane(msg[1])
        elif kind == "action":
            if msg[1] == "jump":
                player.action_jump()    # beendet ein laufendes Ducken selbst
            if msg[1] == "slide":
                player.action_slide()
            if msg[1] == "stand":
                player.action_stand()

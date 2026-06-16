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

Beispiel-Sender:
    from pythonosc.udp_client import SimpleUDPClient
    client = SimpleUDPClient("192.168.137.1", 9000)
    client.send_message("/game/vision/center", [])
    client.send_message("/game/voice/jump", [])
"""

import queue
import threading

try:
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer
    _OSC_AVAILABLE = True
except ImportError:
    _OSC_AVAILABLE = False

OSC_IP   = "0.0.0.0"     # auf allen Netzwerk-Interfaces lauschen
OSC_PORT = 9000

# Eine Queue pro Steuerquelle
_queues: dict[str, queue.Queue] = {
    "vision": queue.Queue(),
    "voice":  queue.Queue(),
}


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
            _queues[source].put(("lane", n))
        return _h

    def _action(source, name):
        def _h(addr, *args):
            _log(addr, *args)
            _queues[source].put(("action", name))
        return _h

    def _map_namespace(prefix, source):
        dispatcher.map(f"{prefix}/left",   _lane(source, 0))
        dispatcher.map(f"{prefix}/center", _lane(source, 1))
        dispatcher.map(f"{prefix}/right",  _lane(source, 2))
        dispatcher.map(f"{prefix}/jump",   _action(source, "jump"))
        dispatcher.map(f"{prefix}/slide",  _action(source, "slide"))
        dispatcher.map(f"{prefix}/stand",  _action(source, "stand"))

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
    print("[OSC] Vision: /game/vision/{left,center,right,jump,slide,stand}")
    print("[OSC] Voice:  /game/voice/{left,center,right,jump,slide,stand}")
    return True


def clear_actions() -> None:
    """Alle gepufferten OSC-Aktionen verwerfen (z. B. beim Match-Start)."""
    for q in _queues.values():
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break


def poll_actions(player, source: str) -> None:
    """OSC-Aktionen der angegebenen Quelle auf den Spieler anwenden.

    `source` ist "vision" oder "voice". Slide und Sprung sind zeit-/impulsbasiert
    und laufen vollständig durch – eine reale Geste ist kürzer als die in-Game-
    Animation, deshalb wird sie NICHT durch nachfolgende OSC-Events abgebrochen.
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
                player.stop_slide()
                player.action_jump()
            if msg[1] == "slide":
                player.action_slide()
            if msg[1] == "stand":
                player.action_stand()

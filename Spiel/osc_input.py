"""
osc_input.py  –  OSC-Empfänger für Subway Surfer.

OSC-Adressen:
    /game/lane/left     → Spieler in linke Spur
    /game/lane/center   → Spieler in mittlere Spur
    /game/lane/right    → Spieler in rechte Spur
    /game/jump          → Springen
    /game/slide         → Sliden

Beispiel-Sender:
    from pythonosc.udp_client import SimpleUDPClient
    client = SimpleUDPClient("192.168.137.1", 9000)
    client.send_message("/game/lane/center", [])
    client.send_message("/game/jump", [])
"""

import queue
import threading

try:
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer
    _OSC_AVAILABLE = True
except ImportError:
    _OSC_AVAILABLE = False

OSC_IP   = "192.168.137.1"
OSC_PORT = 9000

action_queue: queue.Queue = queue.Queue()


def start_osc_server() -> bool:
    if not _OSC_AVAILABLE:
        print("[OSC] pythonosc nicht installiert – pip install python-osc")
        return False

    dispatcher = Dispatcher()
    def _log(addr, *args):
        print(f"[OSC] {addr}  {list(args)}")

    def _lane(n):
        def _h(addr, *args):
            _log(addr, *args)
            action_queue.put(("lane", n))
        return _h

    def _action(name):
        def _h(addr, *args):
            _log(addr, *args)
            action_queue.put(("action", name))
        return _h

    dispatcher.map("/game/left",   _lane(0))
    dispatcher.map("/game/center", _lane(1))
    dispatcher.map("/game/right",  _lane(2))
    dispatcher.map("/game/jump",        _action("jump"))
    dispatcher.map("/game/slide",       _action("slide"))
    dispatcher.set_default_handler(lambda addr, *a: print(f"[OSC] (unbekannt) {addr}  {list(a)}"))

    try:
        server = ThreadingOSCUDPServer((OSC_IP, OSC_PORT), dispatcher)
    except OSError as e:
        print(f"[OSC] Konnte Server nicht starten: {e}")
        return False

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[OSC] Server läuft auf {OSC_IP}:{OSC_PORT}")
    print("[OSC] Adressen: /game/lane/left  /game/lane/center  /game/lane/right  /game/jump  /game/slide")
    return True


def poll_actions(player) -> None:
    while not action_queue.empty():
        try:
            msg = action_queue.get_nowait()
        except queue.Empty:
            break
        kind = msg[0]
        if kind == "lane":
            player.stop_slide()   # aufstehen wenn Spur gewechselt wird
            player.set_lane(msg[1])
        elif kind == "action":
            if msg[1] == "jump":
                player.stop_slide()   # aufstehen beim Springen
                player.action_jump()
            if msg[1] == "slide":
                player.start_slide()  # bleibt geduckt bis anderer Input kommt

"""
start_einzel_pc.py – Notfall-Modus: Spiel und Kamera-Steuerung auf EINEM PC.

Startet das Kamera-Tracking (CV_Contols/CvMain.py) und danach das Spiel
(Spiel/subway_surfer.py) auf diesem Rechner. Beide reden wie im Aufbau mit zwei
Laptops über OSC – nur eben über 127.0.0.1. Das Kamerabild läuft als kleines
Fenster im Vordergrund über dem Spiel.

    uv run start_einzel_pc.py                       # Kamera 0, Gerät automatisch
    uv run start_einzel_pc.py --camera 1            # externe Kamera
    uv run start_einzel_pc.py --voice               # zusätzlich Sprachsteuerung
    uv run start_einzel_pc.py --spieler 2           # zwei Spieler vor der Kamera
                                                    #   (im Spiel-Menü rechts VISION 2 wählen)
    uv run start_einzel_pc.py --device intel:cpu    # weitere Optionen gehen an CvMain.py

Schließt man das Spiel, wird alles beendet.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
READY_TEXT = "Tracking läuft"     # gibt CvMain.py aus, sobald Kamera + Modell bereit sind
READY_TIMEOUT_S = 180             # erster Start auf Intel: OpenVINO-Export kann dauern


def _port() -> int:
    try:
        return int(json.loads((ROOT / "network.json").read_text(encoding="utf-8")).get("port", 9000))
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        return 9000


def _start(name: str, script: Path, args: list[str], ready: threading.Event | None = None) -> subprocess.Popen:
    """Python-Skript als Kindprozess starten, Ausgabe mit [name] vorne weiterreichen."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1")
    proc = subprocess.Popen([sys.executable, str(script), *args], cwd=script.parent, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")

    def forward():
        for line in proc.stdout:
            print(f"[{name}] {line}", end="", flush=True)
            if ready is not None and READY_TEXT in line:
                ready.set()

    threading.Thread(target=forward, daemon=True).start()
    return proc


def _stop(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Spiel + Kamera-Steuerung auf einem PC (weitere Optionen gehen an CvMain.py, "
                    "z.B. --camera 1, --device intel:gpu, --imgsz 480)")
    parser.add_argument("--voice", action="store_true", help="zusätzlich die Sprachsteuerung starten")
    parser.add_argument("--threads", type=int, default=4,
                        help="CPU-Threads fürs Tracking, falls es auf der CPU läuft (Default 4, "
                             "der Rest bleibt fürs Spiel)")
    args, cv_args = parser.parse_known_args()

    port = str(_port())
    local = ["--ip", "127.0.0.1", "--port", port]
    procs: list[subprocess.Popen] = []
    try:
        ready = threading.Event()
        cv = _start("Kamera", ROOT / "CV_Contols" / "CvMain.py",
                    [*local, "--preview", "klein", "--threads", str(args.threads), *cv_args], ready)
        procs.append(cv)

        # Spiel erst starten, wenn das Tracking läuft – sonst schiebt sich das
        # Kamerafenster beim Öffnen vor das Spiel und schnappt ihm die Tastatur weg
        deadline = time.monotonic() + READY_TIMEOUT_S
        while not ready.wait(0.2):
            if cv.poll() is not None:
                print(f"\nKamera-Tracking hat sich beendet (Code {cv.returncode}) – siehe Meldungen oben. "
                      "Ohne Kamera: Spiel direkt starten (uv run Spiel/subway_surfer.py) und TASTATUR wählen.")
                sys.exit(1)
            if time.monotonic() > deadline:
                print("\nKamera-Tracking meldet sich nicht – starte das Spiel trotzdem.")
                break

        if args.voice:
            procs.append(_start("Sprache", ROOT / "Voice" / "main.py", local))
        game = _start("Spiel", ROOT / "Spiel" / "subway_surfer.py", [])
        procs.append(game)

        while game.poll() is None:
            if cv.poll() is not None and cv in procs:
                print(f"\n[Kamera] beendet (Code {cv.returncode}) – das Spiel läuft weiter, "
                      "steuern geht jetzt nur noch per Tastatur.")
                procs.remove(cv)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        _stop(procs)


if __name__ == "__main__":
    main()

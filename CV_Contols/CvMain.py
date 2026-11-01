import argparse
import json
import time
from pathlib import Path
import cv2
import torch
from ultralytics import YOLO
from pythonosc.udp_client import SimpleUDPClient
import tracker

_PROJECT_DIR = Path(__file__).resolve().parent.parent
_NETWORK_FILE = _PROJECT_DIR / "network.json"
_YOLO_MODEL = _PROJECT_DIR / "yolo26n-pose.pt"

CALIB_DELAY_S = 3.0              # Countdown nach der Auswahl, dann Nasenhöhe messen
RESET_HOLD_S = 1.0               # so lange muss der Reset-Arm oben bleiben
START_HOLD_S = 1.0               # so lange müssen beide Arme für die Start-Geste oben bleiben
TRACK_MAX_DIST_FRACTION = 0.5    # max. Hüft-Sprung pro Frame (Anteil der Körperhöhe)
TRACK_MAX_DIST_FALLBACK = 150    # dasselbe in Pixeln, solange keine Körperhöhe bekannt
# Ist der Spieler verloren, wächst der Suchradius um so viele Pixel pro Sekunde –
# so wird er wiedergefunden, auch wenn er sich während des Aussetzers bewegt hat.
TRACK_REGAIN_PX_PER_S = 600


def _load_network_config() -> tuple[str, int]:
    """Ziel-IP und Port aus network.json lesen. Fehlt die Datei: 127.0.0.1:9000."""
    ip, port = "127.0.0.1", 9000
    try:
        data = json.loads(_NETWORK_FILE.read_text(encoding="utf-8"))
        ip = data.get("target_ip", ip)
        port = int(data.get("port", port))
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, ValueError, OSError) as e:
        print(f"[Netzwerk] {_NETWORK_FILE.name} fehlerhaft ({e}) – nutze {ip}:{port}")
    return ip, port


def _pick_device(override: str) -> str:
    """Wählt Gerät für YOLO. Default: cuda wenn verfügbar, sonst cpu."""
    if override != "auto":
        return override
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def main() -> None:
    default_ip, default_port = _load_network_config()
    parser = argparse.ArgumentParser(description="Pose Tracking mit Webcam oder Link to Windows Kamera")
    parser.add_argument("--camera", type=int, default=0,
                        help="Kamera-Index: 0=integrierte Webcam, 1=erste externe Kamera, 2=nächste verfügbare Kamera (z.B. Handy)")
    parser.add_argument("--device", type=str, default="auto",
                        help="Inference-Gerät: 'auto' (default), 'cuda:0', 'cpu'")
    parser.add_argument("--imgsz", type=int, default=960,
                        help="YOLO-Inferenzauflösung (höher = genauer, langsamer). Default 960.")
    parser.add_argument("--cam-width", type=int, default=1280,
                        help="Kamera-Aufnahmebreite in Pixeln. Default 1280.")
    parser.add_argument("--cam-height", type=int, default=720,
                        help="Kamera-Aufnahmehöhe in Pixeln. Default 720.")
    parser.add_argument("--ip", type=str, default=default_ip,
                        help=f"IP des Spiel-Rechners. Default aus network.json: {default_ip}")
    parser.add_argument("--port", type=int, default=default_port,
                        help=f"OSC-Port des Spiels. Default aus network.json: {default_port}")
    args = parser.parse_args()

    client = SimpleUDPClient(args.ip, args.port)
    print(f"Sende OSC an {args.ip}:{args.port}")

    device = _pick_device(args.device)
    print(f"PyTorch: {torch.__version__} | CUDA verfügbar: {torch.cuda.is_available()}")
    if device.startswith("cuda"):
        try:
            idx = int(device.split(":")[1]) if ":" in device else 0
            print(f"Verwende GPU: {torch.cuda.get_device_name(idx)} "
                  f"(Compute Capability {torch.cuda.get_device_capability(idx)})")
        except Exception as e:
            print(f"GPU-Info konnte nicht gelesen werden: {e}")
    else:
        print("Verwende CPU.")

    model = YOLO(str(_YOLO_MODEL))
    try:
        model.to(device)
    except Exception as e:
        print(f"Konnte Modell nicht auf {device} laden ({e}) – fallback auf CPU.")
        device = "cpu"
        model.to(device)

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  args.cam_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.cam_height)
    print(f"Verwende Kamera-Index: {args.camera}")

    if not cap.isOpened():
        print("Fehler: Webcam konnte nicht geöffnet werden.")
        exit(1)

    real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Kameraauflösung: {real_w}x{real_h} | YOLO imgsz: {args.imgsz}")

    print("Tracking läuft. Mit 'q' beenden. 'r' = Auswahlmodus. "
          "Auswahl: linken Arm heben (YOLO-links) oder Taste 0-9. "
          f"Reset: rechten Arm {RESET_HOLD_S:.0f} s oben halten. "
          f"Spiel starten / zurück ins Menü: beide Arme {START_HOLD_S:.0f} s oben halten.")

    cv2.namedWindow("Pose Tracking", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Pose Tracking", 1920, 1080)

    lane_sender = tracker.LaneSender(client)
    position = "MITTE"
    zustand = "STEHT"
    last_zustand = "STEHT"
    selected_person = None      # YOLO-Index bei der Auswahl (nur zur Anzeige)
    selected_position = None    # None = Auswahlmodus
    selected_reference = None
    calib_deadline = 0.0
    reset_arm_since = None
    start_arms_since = None
    start_sent = False
    lost_since = None           # Zeitpunkt, seit dem der Spieler nicht gefunden wird

    def select(idx: int, huefte_x: float, huefte_y: float, how: str) -> None:
        nonlocal selected_person, selected_position, selected_reference
        nonlocal calib_deadline, reset_arm_since, position, zustand, last_zustand
        nonlocal start_arms_since, start_sent, lost_since
        start_arms_since = None
        start_sent = False
        lost_since = None
        selected_person = idx
        selected_position = (huefte_x, huefte_y)
        selected_reference = tracker.load_reference()
        # Nasen- und Körperhöhe werden nach dem Countdown neu gemessen
        selected_reference["nose_y"] = None
        selected_reference["body_height"] = None
        calib_deadline = time.monotonic() + CALIB_DELAY_S
        reset_arm_since = None
        position, zustand, last_zustand = "MITTE", "STEHT", "STEHT"
        lane_sender.reset()
        print(f"Spieler {idx} {how} ausgewählt – Kalibrierung in {CALIB_DELAY_S:.0f} s")

    def deselect(reason: str) -> None:
        nonlocal selected_person, selected_position, selected_reference, reset_arm_since
        nonlocal lost_since
        selected_person = None
        selected_position = None
        selected_reference = None
        reset_arm_since = None
        lost_since = None
        print(f"{reason} – zurück in Auswahlmodus")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]

        results = model.predict(frame, conf=0.5, verbose=False, device=device, imgsz=args.imgsz)
        annotated = results[0].plot()

        persons = tracker.extract_persons(results)
        now = time.monotonic()

        if selected_position is None:
            # ── Auswahlmodus ─────────────────────────────────────────────
            tracker.draw_person_indices(annotated, persons)
            tracker.draw_selection_prompt(annotated, h, persons)
            cv2.imshow("Pose Tracking", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break

            # Tastenauswahl (0-9)
            selected = tracker.select_person_by_key(key, persons)
            if selected is not None:
                select(selected[0], selected[2], selected[3], "per Taste")
                continue

            # Auswahl per Armheben (linkes Handgelenk laut YOLO)
            for idx, person_kpts, huefte_x, huefte_y in persons:
                if tracker.wrist_raised(person_kpts, "left"):
                    select(idx, huefte_x, huefte_y, "per Armheben")
                    break
            continue

        # ── Tracking-Modus ───────────────────────────────────────────────
        # Suchradius um die letzte bekannte Position. Solange der Spieler
        # verloren ist, wächst er mit der Zeit. Die Kalibrierung bleibt dabei
        # erhalten – nach dem Wiederfinden geht es ohne Countdown weiter.
        body_h = selected_reference.get("body_height")
        max_dist = body_h * TRACK_MAX_DIST_FRACTION if body_h else TRACK_MAX_DIST_FALLBACK
        if lost_since is not None:
            max_dist += TRACK_REGAIN_PX_PER_S * (now - lost_since)
        best_person = tracker.find_best_person(persons, selected_position, max_dist) if persons else None

        if best_person is None:
            if lost_since is None:
                lost_since = now
                print("Spieler verloren – suche weiter (Kalibrierung bleibt erhalten)")
            tracker.draw_player_lost(annotated, h)
            reset_arm_since = None
            start_arms_since = None
        else:
            if lost_since is not None:
                print(f"Spieler nach {now - lost_since:.1f} s wiedergefunden")
                lost_since = None
            person_kpts, huefte_x, huefte_y = best_person
            selected_position = (huefte_x, huefte_y)

            if selected_reference.get("nose_y") is None:
                # Countdown, damit der Spieler Zeit hat, sich in Spielposition zu stellen
                remaining = calib_deadline - now
                if remaining > 0:
                    tracker.draw_countdown(annotated, remaining, h, w)
                elif tracker.visible(person_kpts[0]):
                    # Nur im Speicher – wird bei jeder Auswahl neu gemessen,
                    # daher nicht mehr in player_references.json geschrieben
                    selected_reference["nose_y"] = float(person_kpts[0][1])
                    measured_h, quelle = tracker.measure_body_height(person_kpts)
                    selected_reference["body_height"] = measured_h
                    bh_txt = f"{measured_h:.1f} ({quelle})" if measured_h else f"n/a ({quelle}) → Pixel-Fallback"
                    print(f"Kalibriert: nose_y={selected_reference['nose_y']:.1f}, body_height={bh_txt}")
            else:
                position, zustand = tracker.analyze_person(
                    person_kpts, h, w, client, lane_sender, selected_reference, last_zustand)
                last_zustand = zustand
            tracker.draw_player_status(annotated, huefte_x, huefte_y, position, zustand)

            ref_h = selected_reference.get("body_height")
            left_up = tracker.wrist_raised(person_kpts, "left", ref_h)
            right_up = tracker.wrist_raised(person_kpts, "right", ref_h)
            calibrated = selected_reference.get("nose_y") is not None

            # Start: beide Arme START_HOLD_S oben (erst nach der Kalibrierung).
            # Danach müssen die Arme erst wieder runter, bevor erneut gesendet wird.
            if calibrated and left_up and right_up:
                if start_arms_since is None:
                    start_arms_since = now
                elif not start_sent and now - start_arms_since >= START_HOLD_S:
                    client.send_message("/game/vision/start", [])
                    print("/game/vision/start")
                    start_sent = True
            else:
                start_arms_since = None
                start_sent = False

            # Reset nur durch den Spieler selbst und nur, wenn NUR der rechte Arm
            # RESET_HOLD_S oben bleibt – kurzes Armhochreißen beim Sprung und die
            # Start-Geste (beide Arme) zählen nicht.
            if right_up and not left_up:
                if reset_arm_since is None:
                    reset_arm_since = now
                elif now - reset_arm_since >= RESET_HOLD_S:
                    deselect("Armheben erkannt")
            else:
                reset_arm_since = None

        tracker.draw_tracking_help(annotated, h)
        tracker.draw_selected_player(annotated, selected_person, h)

        num = len(results[0].boxes) if results[0].boxes is not None else 0
        cv2.putText(
            annotated, f"Personen erkannt: {num}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
            0.8, (0, 255, 0), 2
        )

        cv2.imshow("Pose Tracking", annotated)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break
        if key == ord('r') and selected_position is not None:
            deselect("Taste r")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

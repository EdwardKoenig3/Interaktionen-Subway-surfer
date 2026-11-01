import argparse
import importlib.util
import json
import math
import time
from pathlib import Path
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from pythonosc.udp_client import SimpleUDPClient
import camera
import identity
import tracker

_PROJECT_DIR = Path(__file__).resolve().parent.parent
_NETWORK_FILE = _PROJECT_DIR / "network.json"
_YOLO_MODEL = _PROJECT_DIR / "yolo26n-pose.pt"

CALIB_DELAY_S = 3.0              # Countdown nach der Auswahl, dann Nasenhöhe messen
RESET_HOLD_S = 1.0               # so lange muss der Reset-Arm oben bleiben
START_HOLD_S = 1.0               # so lange müssen beide Arme für die Start-Geste oben bleiben
TRACK_MAX_DIST_FRACTION = 0.5    # max. Hüft-Sprung pro Frame (Anteil der Körperhöhe)
TRACK_MAX_DIST_FALLBACK = 150    # dasselbe in Pixeln, solange keine Körperhöhe bekannt
# Ist der Spieler verloren, bevor sein Aussehen gelernt ist (erste Bilder nach
# der Auswahl), wächst der Suchradius um so viele Pixel pro Sekunde. Danach
# entscheidet die Wiedererkennung (identity.py), nicht mehr die Position.
TRACK_REGAIN_PX_PER_S = 600
LOST_PAUSE_S = 0.6               # so lange verloren → Spiel hält an (/game/vision/lost)
TAKEOVER_AFTER_S = 10.0          # so lange verloren → eine andere Person darf übernehmen ...
TAKEOVER_HOLD_S = 2.0            # ... indem sie den linken Arm so lange oben hält

WINDOW = "Pose Tracking"
# "klein": Bild-im-Bild über dem Spiel, wenn alles auf einem PC läuft
PREVIEW_SIZES = {"gross": (1920, 1080), "klein": (640, 360)}


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


def _openvino_available() -> bool:
    return importlib.util.find_spec("openvino") is not None


def _pick_device(override: str) -> str:
    """Wählt Gerät für YOLO. Default: CUDA-GPU, sonst Intel per OpenVINO
    (integrierte Arc-GPU, ohne Intel-GPU die CPU), sonst PyTorch auf der CPU."""
    if override != "auto":
        return override
    if torch.cuda.is_available():
        return "cuda:0"
    if _openvino_available():
        return "intel:gpu"
    return "cpu"


def _openvino_device(device: str) -> str:
    """'intel:gpu' / 'intel:npu' auf ein vorhandenes OpenVINO-Gerät abbilden. Bei
    mehreren GPUs heißen sie GPU.0, GPU.1, … (auch NVIDIA/AMD) – dann die von Intel.
    Gibt es keins, läuft OpenVINO auf der CPU."""
    import openvino as ov
    core = ov.Core()
    kind = device.split(":", 1)[1].upper()
    if kind in core.available_devices:
        return device
    for name in core.available_devices:
        if name.split(".")[0] == kind and "intel" in str(core.get_property(name, "FULL_DEVICE_NAME")).lower():
            return f"intel:{name.lower()}"
    print(f"Keine Intel-{kind} gefunden – OpenVINO rechnet auf der CPU.")
    return "intel:cpu"


def _openvino_model(shape: tuple[int, int]) -> Path:
    """OpenVINO-Fassung des Pose-Modells für Eingaben der Größe `shape` (Höhe, Breite).
    Wird beim ersten Mal exportiert (dauert etwas) und liegt dann neben der .pt –
    bei anderer Größe wird neu exportiert."""
    out_dir = _YOLO_MODEL.with_name(f"{_YOLO_MODEL.stem}_openvino_model")
    meta = out_dir / "metadata.yaml"
    if meta.exists():
        import yaml   # kommt mit ultralytics
        data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
        if list(data.get("imgsz", [])) == list(shape):
            return out_dir
    print(f"Exportiere {_YOLO_MODEL.name} nach OpenVINO ({shape[1]}x{shape[0]}, einmalig) ...")
    return Path(YOLO(str(_YOLO_MODEL)).export(format="openvino", imgsz=list(shape), half=True))


def _load_model(device: str, imgsz: int, cam_w: int, cam_h: int) -> tuple[YOLO, str, int | tuple[int, int]]:
    """Modell für `device` laden → (Modell, tatsächliches Gerät, imgsz für predict).
    Klappt das nicht, geht es mit PyTorch auf der CPU weiter."""
    if device.startswith("intel"):
        if not _openvino_available():
            print("OpenVINO ist nicht installiert (uv sync) – nutze PyTorch auf der CPU.")
        else:
            # Feste Eingabegröße im Seitenverhältnis der Kamera (16:9 → 640x384 statt
            # 640x640): spart ~40 % Rechenzeit, PyTorch macht das von selbst.
            shape = (imgsz, imgsz)
            if cam_w > cam_h:
                shape = (math.ceil(imgsz * cam_h / cam_w / 32) * 32, imgsz)
            try:
                device = _openvino_device(device)
                model = YOLO(str(_openvino_model(shape)), task="pose")
                # Erste Vorhersage lädt das Modell aufs Gerät – Fehler sollen hier auffallen
                model.predict(np.zeros((cam_h, cam_w, 3), np.uint8), verbose=False, device=device, imgsz=shape)
                return model, device, shape
            except Exception as e:
                print(f"OpenVINO auf {device} nicht nutzbar ({e}) – nutze PyTorch auf der CPU.")
        device = "cpu"

    model = YOLO(str(_YOLO_MODEL))
    try:
        model.to(device)
    except Exception as e:
        print(f"Konnte Modell nicht auf {device} laden ({e}) – fallback auf CPU.")
        device = "cpu"
        model.to(device)
    return model, device, imgsz


def main() -> None:
    default_ip, default_port = _load_network_config()
    parser = argparse.ArgumentParser(description="Pose Tracking mit Webcam oder Link to Windows Kamera")
    parser.add_argument("--camera", type=int, default=0,
                        help="Kamera-Index: 0=integrierte Webcam, 1=erste externe Kamera, 2=nächste verfügbare Kamera (z.B. Handy)")
    parser.add_argument("--device", type=str, default="auto",
                        help="Inference-Gerät: 'auto' (default: CUDA-GPU, sonst Intel per OpenVINO, sonst CPU), "
                             "'cuda:0', 'cpu', 'intel:gpu', 'intel:cpu', 'intel:npu'")
    parser.add_argument("--imgsz", type=int, default=None,
                        help="YOLO-Inferenzauflösung (höher = genauer, langsamer). Default 960 auf CUDA, sonst 640.")
    parser.add_argument("--threads", type=int, default=None,
                        help="CPU-Threads für PyTorch (Default: alle Kerne). Weniger lässt dem Spiel Luft, "
                             "wenn es auf demselben PC läuft.")
    parser.add_argument("--preview", choices=list(PREVIEW_SIZES) + ["aus"], default="gross",
                        help="Kamerafenster: 'gross' (default), 'klein' (Bild-im-Bild immer im Vordergrund, "
                             "für einen PC mit Spiel), 'aus' (kein Fenster, Auswahl nur per Geste, Ende mit Strg+C)")
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

    if args.threads:
        torch.set_num_threads(args.threads)
    device = _pick_device(args.device)
    imgsz = args.imgsz or (960 if device.startswith("cuda") else 640)
    print(f"PyTorch: {torch.__version__} | CUDA verfügbar: {torch.cuda.is_available()}")
    if device.startswith("cuda"):
        try:
            idx = int(device.split(":")[1]) if ":" in device else 0
            print(f"Verwende GPU: {torch.cuda.get_device_name(idx)} "
                  f"(Compute Capability {torch.cuda.get_device_capability(idx)})")
        except Exception as e:
            print(f"GPU-Info konnte nicht gelesen werden: {e}")
    elif device.startswith("intel"):
        print(f"Verwende Intel-Hardware über OpenVINO ({device}).")
    else:
        print(f"Verwende CPU ({torch.get_num_threads()} Threads). Tipp: Auf Intel-Laptops ist OpenVINO "
              "(--device intel:gpu) deutlich schneller.")

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  args.cam_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.cam_height)
    print(f"Verwende Kamera-Index: {args.camera}")

    if not cap.isOpened():
        print("Fehler: Webcam konnte nicht geöffnet werden.")
        exit(1)

    real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    model, device, imgsz = _load_model(device, imgsz, real_w, real_h)
    if args.imgsz is None and device == "cpu":
        imgsz = 640   # z.B. CUDA fehlgeschlagen → CPU: 960 wäre dort zu langsam
    print(f"Kameraauflösung: {real_w}x{real_h} | YOLO imgsz: {imgsz} | Gerät: {device}")
    reader = camera.LatestFrameReader(cap)

    print("Tracking läuft. Mit 'q' beenden. 'r' = Auswahlmodus. "
          "Auswahl: linken Arm heben (YOLO-links) oder Taste 0-9. "
          f"Reset: rechten Arm {RESET_HOLD_S:.0f} s oben halten. "
          f"Spiel starten / zurück ins Menü: beide Arme {START_HOLD_S:.0f} s oben halten.", flush=True)

    window = args.preview != "aus"
    if window:
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW, *PREVIEW_SIZES[args.preview])
        if args.preview == "klein":
            cv2.moveWindow(WINDOW, 10, 10)
            cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)

    def show(img) -> int:
        """Vorschau zeigen und gedrückte Taste liefern (ohne Fenster: keine)."""
        if not window:
            return 255
        cv2.imshow(WINDOW, img)
        return cv2.waitKey(1) & 0xFF

    lane_sender = tracker.LaneSender(client)
    lost_sender = tracker.LostSender(client)
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
    lock = identity.PlayerLock()  # merkt sich, wie der Spieler aussieht
    takeover_since = None       # seit wann jemand (bei verlorenem Spieler) den linken Arm hebt
    frame_dt = 0.0              # geglättete Zeit pro Bild (für die FPS-Anzeige)
    last_frame_t = time.perf_counter()

    def select(idx: int, huefte_x: float, huefte_y: float, how: str) -> None:
        nonlocal selected_person, selected_position, selected_reference
        nonlocal calib_deadline, reset_arm_since, position, zustand, last_zustand
        nonlocal start_arms_since, start_sent, lost_since, lock, takeover_since
        start_arms_since = None
        start_sent = False
        lost_since = None
        lock = identity.PlayerLock()
        takeover_since = None
        lost_sender.send(False)
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
        lost_sender.send(False)
        print(f"{reason} – zurück in Auswahlmodus")

    try:
        while True:
            ret, frame = reader.read()
            if not ret:
                print("Kamera liefert keine Bilder mehr.")
                break

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            t0 = time.perf_counter()
            results = model.predict(frame, conf=0.5, verbose=False, device=device, imgsz=imgsz)
            infer_ms = (time.perf_counter() - t0) * 1000
            annotated = results[0].plot()
            frame_dt = 0.9 * frame_dt + 0.1 * (t0 - last_frame_t) if frame_dt else t0 - last_frame_t
            last_frame_t = t0
            tracker.draw_perf(annotated, w, 1.0 / max(frame_dt, 1e-6), infer_ms, device)

            persons = tracker.extract_persons(results)
            now = time.monotonic()

            if selected_position is None:
                # ── Auswahlmodus ─────────────────────────────────────────────
                tracker.draw_person_indices(annotated, persons)
                tracker.draw_selection_prompt(annotated, h, persons)
                key = show(annotated)
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
            # Gesucht wird um die letzte bekannte Position. Ist das Aussehen des
            # Spielers gelernt, zählt nach einem längeren Aussetzer nur noch die
            # Wiedererkennung – eine andere Person übernimmt NICHT einfach die
            # Steuerung. Die Kalibrierung bleibt dabei erhalten.
            body_h = selected_reference.get("body_height")
            max_dist = body_h * TRACK_MAX_DIST_FRACTION if body_h else TRACK_MAX_DIST_FALLBACK
            lost_for = None if lost_since is None else now - lost_since
            if lock.identity.ready:
                best_person = lock.find(frame, persons, selected_position, max_dist, lost_for)
                identity.draw_similarities(annotated, persons, lock.sims)
            else:
                if lost_for is not None:
                    max_dist += TRACK_REGAIN_PX_PER_S * lost_for
                best_person = tracker.find_best_person(persons, selected_position, max_dist) if persons else None
            calibrated = selected_reference.get("nose_y") is not None

            if best_person is None:
                if lost_since is None:
                    lost_since = now
                    print("Spieler verloren – warte, bis er wiedererkannt wird (Kalibrierung bleibt erhalten)")
                lost_for = now - lost_since
                # Spiel anhalten, bis der Spieler wieder da ist (erst nach der Kalibrierung)
                lost_sender.send(calibrated and lost_for >= LOST_PAUSE_S)
                reset_arm_since = None
                start_arms_since = None

                # Lange weg → eine andere Person darf mit dem linken Arm übernehmen
                takeover = lost_for >= TAKEOVER_AFTER_S
                tracker.draw_player_lost(annotated, h, lost_for, TAKEOVER_HOLD_S if takeover else None)
                raiser = next((p for p in persons if tracker.wrist_raised(p[1], "left")), None) if takeover else None
                if raiser is None:
                    takeover_since = None
                elif takeover_since is None:
                    takeover_since = now
                elif now - takeover_since >= TAKEOVER_HOLD_S:
                    select(raiser[0], raiser[2], raiser[3], "per Übernahme (linker Arm)")
            else:
                if lost_since is not None:
                    print(f"Spieler nach {now - lost_since:.1f} s wiedererkannt")
                    lost_since = None
                    takeover_since = None
                lost_sender.send(False)
                person_kpts, huefte_x, huefte_y = best_person
                selected_position = (huefte_x, huefte_y)

                # Aussehen lernen (v.a. während des Countdowns) – nicht, solange
                # sich jemand mit dem Spieler überdeckt, sonst mischen sich die Farben
                if not lock.identity.complete and not identity.overlaps_other(person_kpts, persons):
                    lock.identity.learn(identity.appearance(frame, person_kpts))

                if not calibrated:
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

            key = show(annotated)
            if key == ord('q') or key == 27:
                break
            if key == ord('r') and selected_position is not None:
                deselect("Taste r")
    except KeyboardInterrupt:
        pass
    finally:
        lost_sender.send(False)   # Spiel nicht angehalten zurücklassen
        reader.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

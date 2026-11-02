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
import poses
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

# Kamera-Spieler: OSC-Namespace und Farbe (BGR, wie im Spiel: P1 cyan, P2 orange)
SLOTS = (("/game/vision", (255, 255, 0)), ("/game/vision2", (0, 165, 255)))
POWER_MSG_S = 1.0                # so lange steht "SCHILD!" o.ä. im Kamerabild


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


class PlayerSlot:
    """Ein Kamera-Spieler: Auswahl, Kalibrierung, Wiedererkennung und Gesten → OSC.

    Im 1-Spieler-Modus gibt es einen Platz für das ganze Bild – alles wie bisher.
    Im 2-Spieler-Modus hat jeder Platz eine Bildhälfte (`zone`): Dort wird er
    ausgewählt und dort liegen seine drei Spuren. Platz 2 sendet an /game/vision2/*.
    """

    def __init__(self, num: int, client: SimpleUDPClient, zone: tuple[float, float], labeled: bool):
        self.num = num
        self.prefix, self.color = SLOTS[num - 1]
        self.zone = zone                        # (von, bis) als Anteil der Bildbreite
        self.label = f"P{num}" if labeled else ""
        self.client = client
        self.lane_sender = tracker.LaneSender(client, self.prefix)
        self.action_sender = tracker.ActionSender(client, self.prefix)
        self.lost_sender = tracker.LostSender(client, self.prefix)
        self.selected = False
        self.person_idx = None      # YOLO-Index bei der Auswahl (nur zur Anzeige)
        self.position = None        # letzte Hüftposition
        self.reference = None
        self.calib_deadline = 0.0
        self.lost_since = None      # Zeitpunkt, seit dem der Spieler nicht gefunden wird
        self.lock = identity.PlayerLock()   # merkt sich, wie der Spieler aussieht
        self.poses = poses.PoseTrigger()    # Power-up-Haltungen
        self.takeover_since = None  # seit wann jemand (bei verlorenem Spieler) den linken Arm hebt
        self.reset_arm_since = None
        self.start_arms_since = None
        self.start_ready = False    # Start-Geste lange genug gehalten (gesendet wird in main)
        self.start_sent = False
        self.lane, self.zustand, self.last_zustand = "MITTE", "STEHT", "STEHT"
        self.power_msg = None       # (Text, bis wann) – Rückmeldung im Kamerabild

    @property
    def calibrated(self) -> bool:
        return self.selected and self.reference.get("nose_y") is not None

    def _say(self, text: str) -> None:
        print(f"{self.label}: {text}" if self.label else text)

    def in_zone(self, x: float, w: int) -> bool:
        return self.zone[0] * w <= x <= self.zone[1] * w

    def zone_center(self, w: int) -> int:
        return int(w * (self.zone[0] + self.zone[1]) / 2)

    def select(self, idx: int, huefte_x: float, huefte_y: float, how: str, now: float) -> None:
        self.selected = True
        self.person_idx = idx
        self.position = (huefte_x, huefte_y)
        self.reference = tracker.load_reference()
        # Nasen- und Körperhöhe werden nach dem Countdown neu gemessen
        self.reference["nose_y"] = None
        self.reference["body_height"] = None
        self.calib_deadline = now + CALIB_DELAY_S
        self.lost_since = None
        self.lock = identity.PlayerLock()
        self.poses.reset()
        self.takeover_since = None
        self.reset_arm_since = None
        self.start_arms_since = None
        self.start_ready = self.start_sent = False
        self.lane, self.zustand, self.last_zustand = "MITTE", "STEHT", "STEHT"
        self.lane_sender.reset()
        self.action_sender.reset()
        self.lost_sender.send(False)
        self._say(f"Spieler {idx} {how} ausgewählt – Kalibrierung in {CALIB_DELAY_S:.0f} s")

    def deselect(self, reason: str) -> None:
        self.selected = False
        self.position = None
        self.reference = None
        self.reset_arm_since = None
        self.lost_since = None
        self.start_ready = False
        self.action_sender.update("STEHT")   # ein gehaltenes Ducken sauber beenden
        self.lost_sender.send(False)
        self._say(f"{reason} – zurück in Auswahlmodus")

    def send_start(self) -> None:
        self.client.send_message(f"{self.prefix}/start", [])
        print(f"{self.prefix}/start")
        self.start_sent = True

    def track(self, frame, persons, all_persons, now, annotated, h, w, sig_of):
        """Spieler in diesem Bild suchen und seine Gesten auswerten. `persons` sind
        die noch nicht vergebenen Personen. Gibt die Keypoints der Person zurück, die
        dieser Platz nun belegt – oder None."""
        # Gesucht wird um die letzte bekannte Position. Ist das Aussehen des
        # Spielers gelernt, zählt nach einem längeren Aussetzer nur noch die
        # Wiedererkennung – eine andere Person übernimmt NICHT einfach die
        # Steuerung. Die Kalibrierung bleibt dabei erhalten.
        body_h = self.reference.get("body_height")
        max_dist = body_h * TRACK_MAX_DIST_FRACTION if body_h else TRACK_MAX_DIST_FALLBACK
        lost_for = None if self.lost_since is None else now - self.lost_since
        if self.lock.identity.ready:
            best = self.lock.find(frame, persons, self.position, max_dist, lost_for,
                                  sigs=[sig_of(p[1]) for p in persons])
            identity.draw_similarities(annotated, persons, self.lock.sims,
                                       label=self.label or "ID", row=self.num - 1)
        else:
            if lost_for is not None:
                max_dist += TRACK_REGAIN_PX_PER_S * lost_for
            best = tracker.find_best_person(persons, self.position, max_dist) if persons else None

        if best is None:
            return self._lost(persons, now, annotated, h, w)
        self._found(best, all_persons, now, annotated, h, w, sig_of)
        return best[0]

    def _lost(self, persons, now, annotated, h, w):
        if self.lost_since is None:
            self.lost_since = now
            self._say("Spieler verloren – warte, bis er wiedererkannt wird (Kalibrierung bleibt erhalten)")
        lost_for = now - self.lost_since
        # Spiel anhalten, bis der Spieler wieder da ist (erst nach der Kalibrierung)
        self.lost_sender.send(self.calibrated and lost_for >= LOST_PAUSE_S)
        self.reset_arm_since = None
        self.start_arms_since = None
        self.start_ready = False

        # Lange weg → eine andere Person (in seiner Bildhälfte) darf mit dem linken Arm übernehmen
        takeover = lost_for >= TAKEOVER_AFTER_S
        tracker.draw_player_lost(annotated, h, lost_for, TAKEOVER_HOLD_S if takeover else None,
                                 label=self.label, line=self.num - 1)
        raiser = next((p for p in persons
                       if self.in_zone(p[2], w) and tracker.wrist_raised(p[1], "left")), None) if takeover else None
        if raiser is None:
            self.takeover_since = None
        elif self.takeover_since is None:
            self.takeover_since = now
        elif now - self.takeover_since >= TAKEOVER_HOLD_S:
            self.select(raiser[0], raiser[2], raiser[3], "per Übernahme (linker Arm)", now)
            return raiser[1]
        return None

    def _found(self, best, all_persons, now, annotated, h, w, sig_of):
        person_kpts, huefte_x, huefte_y = best
        if self.lost_since is not None:
            self._say(f"Spieler nach {now - self.lost_since:.1f} s wiedererkannt")
            self.lost_since = None
            self.takeover_since = None
        self.lost_sender.send(False)
        self.position = (huefte_x, huefte_y)

        # Aussehen lernen (v.a. während des Countdowns) – nicht, solange sich
        # jemand mit dem Spieler überdeckt, sonst mischen sich die Farben
        if not self.lock.identity.complete and not identity.overlaps_other(person_kpts, all_persons):
            self.lock.identity.learn(sig_of(person_kpts))

        status_color = self.color if self.label else (0, 255, 255)
        if not self.calibrated:
            # Countdown, damit der Spieler Zeit hat, sich in Spielposition zu stellen
            remaining = self.calib_deadline - now
            if remaining > 0:
                tracker.draw_countdown(annotated, remaining, h, w, cx=self.zone_center(w), color=status_color)
            elif tracker.visible(person_kpts[0]):
                # Nur im Speicher – wird bei jeder Auswahl neu gemessen,
                # daher nicht mehr in player_references.json geschrieben
                self.reference["nose_y"] = float(person_kpts[0][1])
                measured_h, quelle = tracker.measure_body_height(person_kpts)
                self.reference["body_height"] = measured_h
                bh_txt = f"{measured_h:.1f} ({quelle})" if measured_h else f"n/a ({quelle}) → Pixel-Fallback"
                self._say(f"Kalibriert: nose_y={self.reference['nose_y']:.1f}, body_height={bh_txt}")
        else:
            self.lane, self.zustand = tracker.analyze_person(
                person_kpts, w, self.lane_sender, self.action_sender, self.reference,
                self.last_zustand, self.zone)
            self.last_zustand = self.zustand
            # Power-ups per Körperhaltung – die Abklingzeit verwaltet das Spiel
            power = self.poses.update(person_kpts, now)
            if power is not None:
                self.client.send_message(f"{self.prefix}/power", [power])
                print(f"{self.prefix}/power {power}")
                self.power_msg = (f"{poses.LABELS[power]}!", now + POWER_MSG_S)
        tracker.draw_player_status(annotated, huefte_x, huefte_y, self.lane, self.zustand,
                                   label=self.label, color=status_color)
        self._draw_power(annotated, person_kpts, now)

        ref_h = self.reference.get("body_height")
        left_up = tracker.wrist_raised(person_kpts, "left", ref_h)
        right_up = tracker.wrist_raised(person_kpts, "right", ref_h)

        # Start: beide Arme START_HOLD_S oben (erst nach der Kalibrierung). Gesendet
        # wird in main(), sobald alle Spieler bereit sind. Danach müssen die Arme
        # erst wieder runter, bevor erneut gesendet wird.
        if self.calibrated and left_up and right_up:
            if self.start_arms_since is None:
                self.start_arms_since = now
            self.start_ready = now - self.start_arms_since >= START_HOLD_S
        else:
            self.start_arms_since = None
            self.start_ready = False
            self.start_sent = False

        # Reset nur durch den Spieler selbst und nur, wenn NUR der rechte Arm
        # RESET_HOLD_S oben bleibt – kurzes Armhochreißen beim Sprung und die
        # Start-Geste (beide Arme) zählen nicht.
        if right_up and not left_up:
            if self.reset_arm_since is None:
                self.reset_arm_since = now
            elif now - self.reset_arm_since >= RESET_HOLD_S:
                self.deselect("Armheben erkannt")
        else:
            self.reset_arm_since = None

    def _draw_power(self, annotated, person_kpts, now) -> None:
        """Über dem Kopf: Fortschritt einer gehaltenen Power-up-Haltung bzw. "SCHILD!"."""
        x, y = float(person_kpts[0][0]), float(person_kpts[0][1]) - 60
        progress = self.poses.progress(now)
        if progress is not None:
            poses.draw_progress(annotated, x, y, progress[0], progress[1], self.color)
        elif self.power_msg is not None and now < self.power_msg[1]:
            cv2.putText(annotated, self.power_msg[0], (int(x) - 70, int(y) - 48),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, self.color, 3)


def _make_slots(n: int, client: SimpleUDPClient) -> list[PlayerSlot]:
    """1 Spieler: ganzes Bild. 2 Spieler: linke Hälfte P1, rechte Hälfte P2."""
    zones = [(0.0, 1.0)] if n == 1 else [(0.0, 0.5), (0.5, 1.0)]
    return [PlayerSlot(i + 1, client, zone, labeled=n > 1) for i, zone in enumerate(zones)]


def _mode_hint(n: int) -> str:
    if n == 1:
        return "Modus: 1 Spieler vor der Kamera (Taste M: 2 Spieler)."
    return ("Modus: 2 Spieler vor der Kamera – links P1 (VISION), rechts P2 (VISION 2). "
            "Im Spiel-Menü 2 Spieler mit rechts VISION 2 wählen. Taste M: 1 Spieler.")


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
    parser.add_argument("--spieler", type=int, choices=(1, 2), default=1,
                        help="Spieler vor der Kamera: 1 (default, wie bisher) oder 2 – dann teilen sie sich "
                             "das Bild: links P1 (/game/vision), rechts P2 (/game/vision2). Umschalten im Fenster: M")
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
          f"Spiel starten / zurück ins Menü: beide Arme {START_HOLD_S:.0f} s oben halten. "
          "Power-ups: Hände vor die Brust (Schild), Arme ausbreiten (Gleiten), "
          "Hände in die Hüften (Magnet).", flush=True)

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

    slots = _make_slots(args.spieler, client)
    print(_mode_hint(len(slots)))
    frame_dt = 0.0              # geglättete Zeit pro Bild (für die FPS-Anzeige)
    last_frame_t = time.perf_counter()

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

            # Farbprofile höchstens einmal pro Person und Bild berechnen
            sig_cache = {}

            def sig_of(kpts):
                if id(kpts) not in sig_cache:
                    sig_cache[id(kpts)] = identity.appearance(frame, kpts)
                return sig_cache[id(kpts)]

            # ── Ausgewählte Spieler verfolgen ────────────────────────────────
            # Zuerst die gerade sichtbaren – ein verlorener Spieler darf nicht die
            # Person übernehmen, die ein anderer Platz schon verfolgt.
            claimed = set()
            for slot in sorted((s for s in slots if s.selected), key=lambda s: s.lost_since is not None):
                avail = [p for p in persons if id(p[1]) not in claimed]
                kpts = slot.track(frame, avail, persons, now, annotated, h, w, sig_of)
                if kpts is not None:
                    claimed.add(id(kpts))

            # Start-Geste erst senden, wenn alle Spieler ausgewählt und kalibriert sind
            if all(s.calibrated for s in slots):
                for s in slots:
                    if s.start_ready and not s.start_sent:
                        s.send_start()

            # ── Freie Plätze: Auswahl per Armheben (linkes Handgelenk laut YOLO) ─
            # Im 2-Spieler-Modus in der Bildhälfte des Platzes. Wer wie ein gerade
            # verlorener Spieler aussieht, wird nicht neu vergeben.
            lost_slots = [s for s in slots if s.selected and s.lost_since is not None
                          and s.lock.identity.ready]

            def looks_like_lost(p):
                return any((s.lock.identity.similarity(sig_of(p[1])) or 0.0) >= identity.SIM_ACCEPT
                           for s in lost_slots)

            free = [s for s in slots if not s.selected]
            candidates = [p for p in persons if id(p[1]) not in claimed and not looks_like_lost(p)] if free else []
            for p in candidates:
                slot = next((s for s in free if s.in_zone(p[2], w)), None)
                if slot is not None and tracker.wrist_raised(p[1], "left"):
                    slot.select(p[0], p[2], p[3], "per Armheben", now)
                    free.remove(slot)
                    claimed.add(id(p[1]))
            candidates = [p for p in candidates if id(p[1]) not in claimed]

            # ── Anzeige ───────────────────────────────────────────────────────
            two = len(slots) > 1
            tracker.draw_zones(annotated, [s.zone for s in slots], [s.label for s in slots],
                               [s.color for s in slots])
            if free:
                tracker.draw_person_indices(annotated, candidates)
                if not two:
                    tracker.draw_selection_prompt(annotated, h, candidates)
            tracker.draw_tracking_help(annotated, h, "R = Auswahlmodus | M = 1/2 Spieler | Q = Beenden")

            num = len(results[0].boxes) if results[0].boxes is not None else 0
            cv2.putText(
                annotated, f"Personen erkannt: {num}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 255, 0), 2
            )
            if not two:
                tracker.draw_selected_player(annotated, slots[0].person_idx if slots[0].selected else None, h)
            else:
                for i, s in enumerate(slots):
                    side = "linken" if i == 0 else "rechten"
                    if not s.selected:
                        text = f"{s.label}: frei - linken Arm in der {side} Bildhaelfte heben"
                    elif s.lost_since is not None:
                        text = f"{s.label}: verloren - warte auf dieselbe Person"
                    elif not s.calibrated:
                        text = f"{s.label}: Spieler {s.person_idx} - Kalibrierung"
                    else:
                        text = f"{s.label}: Spieler {s.person_idx} bereit"
                    cv2.putText(annotated, text, (10, 60 + 30 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.8, s.color, 2)

            key = show(annotated)
            if key == ord('q') or key == 27:
                break
            if key == ord('r'):
                for s in slots:
                    if s.selected:
                        s.deselect("Taste r")
            elif key == ord('m'):
                for s in slots:
                    if s.selected:
                        s.deselect("Modus gewechselt")
                slots = _make_slots(1 if two else 2, client)
                print(_mode_hint(len(slots)))
            elif free:
                # Tastenauswahl (0-9): in den Platz der Bildhälfte, sonst den ersten freien
                selected = tracker.select_person_by_key(key, candidates)
                if selected is not None:
                    slot = next((s for s in free if s.in_zone(selected[2], w)), free[0])
                    slot.select(selected[0], selected[2], selected[3], "per Taste", now)
    except KeyboardInterrupt:
        pass
    finally:
        for s in slots:
            s.lost_sender.send(False)   # Spiel nicht angehalten zurücklassen
        reader.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

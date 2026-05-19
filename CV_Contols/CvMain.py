import argparse
import cv2
import torch
from ultralytics import YOLO
from pythonosc.udp_client import SimpleUDPClient
import tracker


def _pick_device(override: str) -> str:
    """Wählt Gerät für YOLO. Default: cuda wenn verfügbar, sonst cpu."""
    if override != "auto":
        return override
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def main() -> None:
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
    args = parser.parse_args()

    IP = "192.168.137.1"
    PORT = 9000
    client = SimpleUDPClient(IP, PORT)

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

    model = YOLO("yolo26n-pose.pt")
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

    print("Tracking läuft. Mit 'q' beenden. Drücke 'r' für Auswahlmodus.")

    cv2.namedWindow("Pose Tracking", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Pose Tracking", 1920, 1080)
    position = "MITTE"
    zustand = "STEHT"
    last_zustand = "STEHT"
    selected_person = None
    selected_position = None
    selected_reference = None
    selection_made = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]

        results = model.predict(frame, conf=0.5, verbose=False, device=device, imgsz=args.imgsz)
        annotated = results[0].plot()

        persons = tracker.extract_persons(results)

        if not selection_made:
            tracker.draw_person_indices(annotated, persons)
            tracker.draw_selection_prompt(annotated, h, persons)
            cv2.imshow("Pose Tracking", annotated)
            key = cv2.waitKey(0) & 0xFF
            if key == ord('q') or key == 27:
                break
            selected = tracker.select_person_by_key(key, persons)
            if selected is not None:
                selected_person = selected[0]
                selected_position = (selected[2], selected[3])
                selected_reference = tracker.load_player_reference(selected_person)
                # Nasenhöhe + Körperhöhe zurücksetzen, um sie neu zu messen
                selected_reference["nose_y"] = None
                selected_reference["body_height"] = None
                selection_made = True
                position = "MITTE"
                zustand = "STEHT"
                last_zustand = "STEHT"
                print(f"Spieler {selected_person} ausgewählt")
                print(f"Verwende Referenz für Spieler {selected_person}: {selected_reference}")
            continue

        if persons and selected_position is not None:
            best_person = tracker.find_best_person(persons, selected_position)
            if best_person is not None:
                person_kpts, huefte_x, huefte_y = best_person
                selected_position = (huefte_x, huefte_y)
                
                # Nasen- + Körperhöhe beim ersten Frame im Stand kalibrieren
                if selected_reference.get("nose_y") is None and person_kpts[0][1] > 0:
                    selected_reference["nose_y"] = float(person_kpts[0][1])
                    body_h = tracker.measure_body_height(person_kpts)
                    if body_h:
                        selected_reference["body_height"] = body_h
                    tracker.save_player_reference(selected_person, selected_reference)
                    bh_txt = f"{body_h:.1f}" if body_h else "n/a (Knöchel nicht sichtbar → Pixel-Fallback)"
                    print(f"Kalibriert Spieler {selected_person}: "
                          f"nose_y={selected_reference['nose_y']:.1f}, body_height={bh_txt}")
                
                position, zustand = tracker.analyze_person(person_kpts, h, w, client, position, selected_reference, last_zustand)
                last_zustand = zustand
                tracker.draw_player_status(annotated, huefte_x, huefte_y, position, zustand)
        elif not persons:
            tracker.draw_no_person(annotated, h)

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
        if key == ord('q'):
            break
        if key == ord('r'):
            selection_made = False
            selected_person = None
            selected_position = None
            position = "MITTE"
            zustand = "STEHT"
            last_zustand = "STEHT"
            selected_reference = None
            print("Zurück in Auswahlmodus")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

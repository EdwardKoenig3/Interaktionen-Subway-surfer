import argparse
import cv2
from ultralytics import YOLO
from pythonosc.udp_client import SimpleUDPClient
import tracker


def main() -> None:
    parser = argparse.ArgumentParser(description="Pose Tracking mit Webcam oder Link to Windows Kamera")
    parser.add_argument("--camera", type=int, default=0,
                        help="Kamera-Index: 0=integrierte Webcam, 1=erste externe Kamera, 2=nächste verfügbare Kamera (z.B. Handy)")
    args = parser.parse_args()

    IP = "192.168.137.1"
    PORT = 9000
    client = SimpleUDPClient(IP, PORT)

    model = YOLO("yolo26n-pose.pt")

    cap = cv2.VideoCapture(args.camera)
    print(f"Verwende Kamera-Index: {args.camera}")

    if not cap.isOpened():
        print("Fehler: Webcam konnte nicht geöffnet werden.")
        exit(1)

    print("Tracking läuft. Mit 'q' beenden. Drücke 'r' für Auswahlmodus.")

    cv2.namedWindow("Pose Tracking", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Pose Tracking", 800, 450)
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

        results = model.predict(frame, conf=0.5, verbose=False)
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
                # Nasenhöhe-Referenz zurücksetzen, um sie neu zu messen
                selected_reference["nose_y"] = None
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
                
                # Nasenhöhe beim ersten Frame speichern, falls noch nicht vorhanden
                if selected_reference.get("nose_y") is None and person_kpts[0][1] > 0:
                    selected_reference["nose_y"] = float(person_kpts[0][1])
                    tracker.save_player_reference(selected_person, selected_reference)
                    print(f"Nasenhöhe-Referenz für Spieler {selected_person} gespeichert: {selected_reference['nose_y']:.1f}")
                
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

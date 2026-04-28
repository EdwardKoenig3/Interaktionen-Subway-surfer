import argparse
import cv2
from ultralytics import YOLO
from pythonosc.udp_client import SimpleUDPClient


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

    print("Tracking läuft. Mit 'q' beenden.")

    cv2.namedWindow("Pose Tracking", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Pose Tracking", 800, 450)
    position = "MITTE"

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]

        results = model.predict(frame, conf=0.5, verbose=False)
        annotated = results[0].plot()

        if results[0].keypoints is not None and len(results[0].keypoints.xy) > 0:
            for person_kpts in results[0].keypoints.xy:

                if len(person_kpts) >= 17:
                    # Wichtige Punkte
                    li_huefte = person_kpts[11]
                    re_huefte = person_kpts[12]
                    li_knie = person_kpts[13]
                    re_knie = person_kpts[14]
                    li_knoechel = person_kpts[15]
                    re_knoechel = person_kpts[16]

                    # Mittelpunkt Hüfte
                    if li_huefte[0] > 0 and re_huefte[0] > 0:
                        huefte_x = float((li_huefte[0] + re_huefte[0]) / 2)
                        huefte_y = float((li_huefte[1] + re_huefte[1]) / 2)
                    else:
                        continue

                    # -------------------
                    # 📍 POSITION (Drittel)
                    # -------------------
                    if huefte_x < w / 3:
                        if position != "LINKS":
                            client.send_message("/game/left", [])
                            print("/game/left")
                        position = "LINKS"
                    elif huefte_x < 2 * w / 3:
                        if position != "MITTE":
                            client.send_message("/game/center", [])
                            print("/game/center")
                        position = "MITTE"
                    else:
                        if position != "RECHTS":
                            client.send_message("/game/right", [])
                            print("/game/right")
                        position = "RECHTS"


                    # -------------------
                    # 🏃 HALTUNG
                    # -------------------
                    zustand = "STEHT"

                    if (li_knie[1] > 0 and re_knie[1] > 0 and
                        li_huefte[1] > 0 and re_huefte[1] > 0):

                        knie_y = (li_knie[1] + re_knie[1]) / 2
                        huefte_y = (li_huefte[1] + re_huefte[1]) / 2

                        # Hocke: Hüfte nahe an Knie
                        if abs(huefte_y - knie_y) < 60:
                            if zustand != "SLIDE":
                                client.send_message("/game/slide", [])
                                print("/game/slide")
                            zustand = "SLIDE"

                    # Sprung: Füße deutlich höher als normal
                    if (li_knoechel[1] > 0 and re_knoechel[1] > 0):
                        knoechel_y = (li_knoechel[1] + re_knoechel[1]) / 2

                        # Wenn Füße ungewöhnlich hoch → Sprung
                        if knoechel_y < h * 0.75:
                            if zustand != "JUMP":
                                client.send_message("/game/jump", [])
                                print("/game/jump")
                            zustand = "JUMP"
                            

                    # -------------------
                    # 🖥️ Ausgabe
                    # -------------------
                    text = f"{position} | {zustand}"

                    cv2.putText(
                        annotated, text,
                        (int(huefte_x) - 80, int(huefte_y) - 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 255), 2
                    )

        num = len(results[0].boxes) if results[0].boxes is not None else 0

        cv2.putText(
            annotated, f"Personen erkannt: {num}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
            0.8, (0, 255, 0), 2
        )

        cv2.imshow("Pose Tracking", annotated)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
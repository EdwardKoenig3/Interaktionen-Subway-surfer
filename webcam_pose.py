"""
Webcam-Prototyp mit Pose-Erkennung (Gesichts-Keypoints)
========================================================
Erkennt Personen und zeichnet 17 Keypoints ein, darunter:
- Nase
- Linkes Auge, rechtes Auge
- Linkes Ohr, rechtes Ohr
- Schultern, Ellbogen, Handgelenke, Hüfte, Knie, Knöchel

Mit 'q' beenden.
"""

import cv2
from ultralytics import YOLO

# Pose-Modell laden (statt Detection)
# yolo11n-pose.pt hat einen extra "Kopf" der Keypoints vorhersagt
model = YOLO("yolo11n-pose.pt")

# COCO Pose Keypoint-Namen (Reihenfolge wichtig!)
KEYPOINT_NAMES = [
    "Nase", "li_Auge", "re_Auge", "li_Ohr", "re_Ohr",
    "li_Schulter", "re_Schulter", "li_Ellbogen", "re_Ellbogen",
    "li_Handgelenk", "re_Handgelenk", "li_Hüfte", "re_Hüfte",
    "li_Knie", "re_Knie", "li_Knöchel", "re_Knöchel"
]

# Indices der "Gesichts"-Keypoints (Nase, Augen, Ohren)
GESICHT_IDX = [0, 1, 2, 3, 4]

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Fehler: Webcam konnte nicht geöffnet werden.")
    exit(1)

print("Pose-Tracking läuft. Mit 'q' beenden.")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Inferenz
    results = model.predict(frame, conf=0.5, verbose=False)

    # Ultralytics zeichnet das Skelett automatisch
    annotated = results[0].plot()

    # Zusätzliche Logik: Blick-Richtung grob schätzen
    # (basierend auf Nasen-Position relativ zu den Augen)
    if results[0].keypoints is not None and len(results[0].keypoints.xy) > 0:
        for person_kpts in results[0].keypoints.xy:
            # person_kpts ist ein Tensor mit 17 x (x,y) Koordinaten
            if len(person_kpts) >= 5:
                nase = person_kpts[0]
                li_auge = person_kpts[1]
                re_auge = person_kpts[2]

                # Keypoints können 0,0 sein wenn nicht erkannt
                if nase[0] > 0 and li_auge[0] > 0 and re_auge[0] > 0:
                    # Mittelpunkt zwischen den Augen
                    augen_mitte_x = (li_auge[0] + re_auge[0]) / 2

                    # Wenn Nase deutlich links/rechts der Augenmitte → Kopf gedreht
                    offset = float(nase[0] - augen_mitte_x)
                    augen_abstand = abs(float(li_auge[0] - re_auge[0])) + 1

                    ratio = offset / augen_abstand
                    if ratio < -0.15:
                        richtung = "schaut nach RECHTS"
                    elif ratio > 0.15:
                        richtung = "schaut nach LINKS"
                    else:
                        richtung = "schaut GERADEAUS"

                    # An Nasen-Position ausgeben
                    cv2.putText(
                        annotated, richtung,
                        (int(nase[0]) - 60, int(nase[1]) - 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 255), 2
                    )

    # Info oben
    num = len(results[0].boxes) if results[0].boxes is not None else 0
    cv2.putText(
        annotated, f"Personen erkannt: {num}",
        (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
        0.8, (0, 255, 0), 2
    )
    cv2.putText(
        annotated, "q = beenden",
        (10, 60), cv2.FONT_HERSHEY_SIMPLEX,
        0.6, (200, 200, 200), 1
    )

    cv2.imshow("YOLO11 Pose - Webcam Test", annotated)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

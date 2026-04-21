"""
Minimaler Webcam-Prototyp mit YOLO11
=====================================
Öffnet die Webcam und erkennt Personen (und 79 weitere COCO-Klassen).
Mit 'q' beenden.

Nur zum Testen ob dein Setup funktioniert — nicht für Produktion.
"""

import cv2
from ultralytics import YOLO

# Nano-Modell laden (klein und schnell, ~6 MB)
# Wird beim ersten Aufruf automatisch heruntergeladen
model = YOLO("yolo11n.pt")

# Webcam öffnen (0 = Standard-Kamera)
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Fehler: Webcam konnte nicht geöffnet werden.")
    exit(1)

print("Webcam läuft. Mit 'q' beenden.")

while True:
    # Frame von der Webcam holen
    ret, frame = cap.read()
    if not ret:
        break

    # YOLO über das Frame laufen lassen
    # classes=[0] filtert nur "person" (Klasse 0 in COCO)
    # Wenn du alles sehen willst, lass classes weg
    results = model.predict(
        frame,
        conf=0.5,        # Mindest-Konfidenz 50%
        classes=[0],     # Nur Personen (entfernen für alle Objekte)
        verbose=False,   # Keine Konsolen-Spam
    )

    # YOLO zeichnet Boxen und Labels automatisch
    annotated = results[0].plot()

    # Anzahl erkannter Personen oben links einblenden
    num_persons = len(results[0].boxes) if results[0].boxes is not None else 0
    cv2.putText(
        annotated,
        f"Personen: {num_persons}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1, (0, 255, 0), 2
    )

    # Anzeigen
    cv2.imshow("YOLO11 - Webcam Test (q = quit)", annotated)

    # 'q' zum Beenden
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Aufräumen
cap.release()
cv2.destroyAllWindows()

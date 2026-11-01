# Interaktionen-Subway-surfer
Dieses Repository beinhalten den Code für das Interaktionen Praktikum Projekt worin wir ein Spiel bauen das anhand von Gesten gesteuert wird.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `Spiel/` | 3D-Spiel (Ursina), empfängt Befehle per OSC auf Port 9000 |
| `CV_Contols/` | Kamera-Steuerung: YOLO-Pose → Spur, Sprung, Ducken, Start-Geste → OSC `/game/vision/*` |
| `Voice/` | Sprachsteuerung (Vosk) → OSC `/game/voice/*` |

Einmalig: `uv sync` (installiert alles, auf Intel-Laptops auch OpenVINO).

## Starten

**Zwei Rechner (Normalfall):** In `network.json` die IP des Spiel-Rechners eintragen, dann

```
uv run Spiel/subway_surfer.py        # Spiel-Rechner
uv run CV_Contols/CvMain.py          # Kamera-Rechner
```

**Ein Rechner (Notfall):** Spiel und Kamera-Steuerung laufen zusammen, das Kamerabild als kleines Fenster über dem Spiel:

```
uv run start_einzel_pc.py                  # Kamera 0
uv run start_einzel_pc.py --camera 1       # externe Kamera
uv run start_einzel_pc.py --voice          # zusätzlich Sprachsteuerung (2-Spieler-Modus)
```

Weitere Optionen werden an `CvMain.py` durchgereicht (z.B. `--device intel:cpu`, `--imgsz 480`). Schließt man das Spiel, endet alles.

## Kamera-Steuerung

- **Auswahl:** linken Arm heben (oder Taste 0–9 im Kamerafenster). Danach 3 s gerade hinstellen – dabei werden Nasenhöhe, Körpergröße und das **Aussehen** (Kleidungsfarben) gelernt.
- **Wiedererkennung:** Die Steuerung bleibt bei der gewählten Person. Ist sie kurz weg (aus dem Bild, verdeckt), springt die Steuerung **nicht** auf jemand anderen – auch nicht, wenn sonst nur eine Person im Bild steht. Das Spiel hält an („SPIELER NICHT ERKANNT“), bis dieselbe Person wieder erkannt wird, und läuft dann weiter. Die Zahl `ID 0.xx` unter jeder Person im Kamerabild zeigt die Ähnlichkeit (grün = wird erkannt).
- **Neuer Spieler:** eigene Abmeldung mit rechtem Arm 1 s hoch, Taste `R` – oder wenn der alte Spieler über 10 s weg ist: linken Arm 2 s hochhalten.
- **Start / zurück ins Menü:** beide Arme 1 s hoch.

Grenze: Zwei Personen mit fast gleicher Kleidung (z.B. beide ganz in Schwarz) sind nur schwer zu unterscheiden. Die Schwellen stehen oben in `CV_Contols/identity.py`.

## Rechenleistung

Ohne NVIDIA-GPU nutzt `CvMain.py` automatisch OpenVINO (Intel-GPU, sonst CPU) und eine kleinere Auflösung (640 statt 960). Beim ersten Start wird das Modell dafür einmal umgewandelt. FPS und Rechenzeit stehen oben rechts im Kamerabild. Messen, was der Rechner schafft:

```
uv run CV_Contols/benchmark.py
```

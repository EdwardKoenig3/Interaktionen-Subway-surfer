# Interaktionen-Subway-surfer
Dieses Repository beinhalten den Code für das Interaktionen Praktikum Projekt worin wir ein Spiel bauen das anhand von Gesten gesteuert wird.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `Spiel/` | 3D-Spiel (Ursina), empfängt Befehle per OSC auf Port 9000 |
| `CV_Contols/` | Kamera-Steuerung: YOLO-Pose → Spur, Sprung, Ducken, Power-ups, Start-Geste → OSC `/game/vision/*` (2. Kamera-Spieler: `/game/vision2/*`) |
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
uv run start_einzel_pc.py --spieler 2      # zwei Spieler vor einer Kamera (siehe unten)
```

Weitere Optionen werden an `CvMain.py` durchgereicht (z.B. `--device intel:cpu`, `--imgsz 480`). Schließt man das Spiel, endet alles.

## Kamera-Steuerung

- **Auswahl:** linken Arm heben (oder Taste 0–9 im Kamerafenster). Danach 3 s gerade hinstellen – dabei werden Nasenhöhe, Körpergröße und das **Aussehen** (Kleidungsfarben) gelernt.
- **Wiedererkennung:** Die Steuerung bleibt bei der gewählten Person. Ist sie kurz weg (aus dem Bild, verdeckt), springt die Steuerung **nicht** auf jemand anderen – auch nicht, wenn sonst nur eine Person im Bild steht. Das Spiel hält an („SPIELER NICHT ERKANNT“), bis dieselbe Person wieder erkannt wird, und läuft dann weiter. Die Zahl `ID 0.xx` unter jeder Person im Kamerabild zeigt die Ähnlichkeit (grün = wird erkannt).
- **Neuer Spieler:** eigene Abmeldung mit rechtem Arm 1 s hoch, Taste `R` – oder wenn der alte Spieler über 10 s weg ist: linken Arm 2 s hochhalten.
- **Start / zurück ins Menü:** beide Arme 1 s hoch.
- **Ducken:** Die Figur rutscht, solange man unten bleibt – mindestens 1,5 s (Sprache: immer 1,5 s).

Grenze: Zwei Personen mit fast gleicher Kleidung (z.B. beide ganz in Schwarz) sind nur schwer zu unterscheiden. Die Schwellen stehen oben in `CV_Contols/identity.py`.

### Power-ups

Haltung ½ s halten – danach wirkt das Power-up und klingt ab, bevor es wieder geht. Oben links neben dem Punktestand stehen die drei Symbole: normal = bereit, groß mit gelber Zahl = wirkt noch so viele Sekunden, dunkel mit Zahl = klingt noch ab.

| Haltung | Power-up | Wirkung | Dauer / Abklingzeit | Tastatur |
|---|---|---|---|---|
| Hände vor der Brust (oder Arme kreuzen) | **Schild** | fängt den nächsten Treffer ab | 8 s / 25 s | Q bzw. J |
| Arme seitlich ausbreiten | **Gleiten** | hoher, schwebender Sprung – über Züge und Balken | 2,5 s / 15 s | E bzw. K |
| Hände in die Hüften | **Magnet** | zieht Münzen aus allen Spuren an | 8 s / 20 s | F bzw. L |

Im Menü schaltet `U` die Power-ups ab – dann spielt sich alles wie bisher (z.B. fair im Duell VISION gegen VOICE, Sprache hat keine Power-ups). Werte in `Spiel/powerups.py`, Haltungen in `CV_Contols/poses.py`.

### Zwei Spieler vor einer Kamera

1. Kamera-Tracking im 2-Spieler-Modus starten: `--spieler 2` (oder im Kamerafenster Taste `M`).
2. Im Spiel-Menü mit `TAB` auf 2 Spieler, mit `2` rechts **VISION 2** wählen.

Jeder hat eine Bildhälfte: links P1 (cyan), rechts P2 (orange). Dort hebt man den linken Arm zum Mitspielen, dort liegen die eigenen drei Spuren (Linien im Kamerabild). Gestartet wird erst, wenn beide kalibriert sind. Die Wiedererkennung läuft für jeden getrennt – ist einer weg, hält das Spiel an.

**Wie bisher** (eine Person per Kamera, die andere per Sprache oder Tastatur): Kamera-Tracking ohne `--spieler 2` starten und im Menü rechts VOICE bzw. TASTATUR wählen.

## Spiel

Manche Züge haben vorne eine Holzrampe: einfach in der Spur bleiben, dann läuft man ohne Sprung aufs Dach.

## Rechenleistung

Ohne NVIDIA-GPU nutzt `CvMain.py` automatisch OpenVINO (Intel-GPU, sonst CPU) und eine kleinere Auflösung (640 statt 960). Beim ersten Start wird das Modell dafür einmal umgewandelt. FPS und Rechenzeit stehen oben rechts im Kamerabild. Messen, was der Rechner schafft:

```
uv run CV_Contols/benchmark.py
```

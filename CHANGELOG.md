# Changelog

Alle Änderungen aus der Arbeitssitzung vom 1./2. November 2026 auf dem Branch
`Einzel_PC_Wiedererkennung`. Bedienung im Detail: siehe [README](README.md).

## Teil 2 – Spielmechaniken und zwei Kamera-Spieler

### Neu

- **Ducken, solange man unten bleibt:** Das Kamera-Tracking meldet Ducken als Zustand
  (`slide` wird wiederholt, `stand` beim Aufstehen). Die Figur rutscht so lange, mindestens
  1,5 s. Geht `stand` verloren, endet das Rutschen spätestens 0,75 s nach der letzten
  Meldung. Bei Sprache bleibt es bei festen 1,5 s.
- **Power-ups per Körperhaltung** (`CV_Contols/poses.py`, `Spiel/powerups.py`) –
  Haltung ½ s halten, danach klingt das Power-up ab, bevor es wieder geht:

  | Haltung | Power-up | Wirkung | Dauer / Abklingzeit |
  |---|---|---|---|
  | Hände vor der Brust (oder Arme kreuzen) | Schild | fängt einen Treffer ab | 8 s / 25 s |
  | Arme seitlich ausbreiten | Gleiten | hoher, schwebender Sprung über Züge | 2,5 s / 15 s |
  | Hände in die Hüften | Magnet | zieht Münzen aus allen Spuren an | 8 s / 20 s |

  - Symbole im HUD zeigen bereit / wirkt / klingt ab (mit Sekunden), an der Figur gibt es
    Schild-Blase, Flügel und Magnet, im Kamerabild einen Fortschrittsbalken beim Halten.
  - Tastatur: Q/E/F (Spieler links bzw. allein), J/K/L (Spieler rechts).
  - Im Menü mit `U` abschaltbar – dann spielt sich alles wie vorher.
  - Haltungen gegen Fehlauslösung geprüft (u.a. Jacke halten, Zeigen, Hände in den Taschen).
- **Rampen auf Züge:** 40 % der Züge haben vorne eine Holzrampe, über die man ohne Sprung
  aufs Dach läuft, oft mit Münzspur. Seitlich betreten geht nur, solange sie noch flach ist.
- **Zwei Spieler vor einer Kamera:** `CvMain.py --spieler 2` (bzw. `start_einzel_pc.py
  --spieler 2` oder Taste `M` im Kamerafenster), im Spiel-Menü rechts **VISION 2**.
  Jeder Spieler hat eine Bildhälfte mit eigenen drei Spuren und eigener Wiedererkennung.
  Gestartet wird erst, wenn beide kalibriert sind. OSC-Namespace des zweiten Spielers:
  `/game/vision2/*`.

### Geändert

- OSC: neue Adressen `/game/vision2/*` und `/game/<quelle>/power <name>`.
- `CvMain.py` in Spielerplätze (`PlayerSlot`) umgebaut, Spurgrenzen im Kamerabild sichtbar.
- HUD: Power-up-Anzeige und Meldungen auf dunklem Hintergrund (vor den Häusern lesbar),
  Herzen überlappen im 2-Spieler-Modus nicht mehr.
- Kamerabild: Auswahlhinweis ohne kaputte Umlaute.

### Unverändert

- 1-Spieler-Modus und der bisherige 2-Spieler-Modus (VISION + VOICE bzw. TASTATUR)
  funktionieren wie vorher, ebenso ältere Sender, die nur `slide` schicken.

### Getestet

- Im echten Spiel (51 Prüfungen: Menü, Ducken, Power-ups, Rampe, Tastatur, beide
  2-Spieler-Modi), Kamera-Tracking mit dem echten YOLO-Modell (1 und 2 Spieler) und die
  Gesamtkette Kamera → OSC → Spiel (2 Spieler; 1 Spieler mit OpenVINO).
- Noch nicht: echte Personen vor einer echten Webcam – vor allem die Power-up-Haltungen
  einmal vormachen; die Schwellen stehen oben in `CV_Contols/poses.py`.

## Teil 1 – Einzel-PC-Modus und Wiedererkennung (Commit `e7d4944`)

### Neu

- **Notfall-Modus mit einem PC:** `start_einzel_pc.py` startet Kamera-Tracking und Spiel
  zusammen, das Kamerabild läuft als kleines Fenster über dem Spiel, optional mit
  Sprachsteuerung (`--voice`).
- **Wiedererkennung des Spielers** (`CV_Contols/identity.py`): merkt sich beim
  Kalibrieren die Kleidungsfarben. Ist der Spieler kurz weg, springt die Steuerung nicht
  auf eine andere Person, sondern wartet, bis er wieder erkannt wird. Nach über 10 s kann
  ein neuer Spieler mit dem linken Arm (2 s) übernehmen.
- **Spiel hält an, solange der Spieler nicht erkannt wird** (`/game/vision/lost 1|0`,
  Hinweis „SPIELER NICHT ERKANNT“). Die Meldung läuft nach 2 s ab, falls das Tracking
  abstürzt.
- **Intel-Laptops (z.B. Core Ultra 7 155H):** ohne NVIDIA-GPU automatisch OpenVINO
  (Intel-GPU, sonst CPU), Export im Seitenverhältnis der Kamera; bei mehreren GPUs wird
  gezielt die Intel-GPU gewählt.
- Kamera wird in einem eigenen Thread gelesen (immer das neueste Bild), FPS-Anzeige im
  Kamerabild, Optionen `--preview gross|klein|aus` und `--threads`.
- `CV_Contols/benchmark.py`: misst die Erkennung auf allen verfügbaren Geräten.

### Geändert

- Standard-Auflösung ohne CUDA 640 statt 960.
- `openvino` als Abhängigkeit, der OpenVINO-Export steht in `.gitignore`.
- README mit Anleitung für beide Aufbauten (zwei Rechner / ein Rechner).

## Hinweise

- `uv.lock` ist noch nicht aktualisiert (neue Abhängigkeit `openvino`) – nach dem
  nächsten `uv sync` mitcommitten.

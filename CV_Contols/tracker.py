import cv2
import json
import time
from pathlib import Path

import numpy as np
from pythonosc.udp_client import SimpleUDPClient
from typing import Any, Dict, List, Optional, Tuple

# (YOLO-Index, Keypoints 17 × [x, y, Konfidenz], Hüfte x, Hüfte y)
TrackedPerson = Tuple[int, Any, float, float]

# Liegt neben tracker.py – unabhängig davon, aus welchem Ordner gestartet wird
_REFERENCE_FILE = str(Path(__file__).resolve().parent / "player_references.json")


# ── Keypoint-Sichtbarkeit ─────────────────────────────────────────────
# Die installierte ultralytics-Version liefert für JEDEN Keypoint eine
# Koordinate – auch für verdeckte oder nicht im Bild liegende (dann geschätzt,
# nicht 0). Ob ein Punkt wirklich erkannt wurde, steht nur in seiner Konfidenz.
# 0.5 = dieselbe Schwelle, ab der YOLO den Punkt im Kamerabild einzeichnet.
KPT_CONF = 0.5

# Sind die Füße nicht im Bild, wird die Körperhöhe (Nase→Knöchel) aus der
# Rumpflänge (Schulter→Hüfte) geschätzt: beim Erwachsenen etwa das 2,9-Fache.
TORSO_TO_BODY = 2.9


# ── Zustandsschwellen ─────────────────────────────────────────────────
# Anteil der kalibrierten Körperhöhe (Nase→Knöchel). Dadurch auflösungs-
# und abstandsunabhängig — egal welche Kameraauflösung oder wie weit weg.
SLIDE_DROP_FRACTION = 0.16   # Nase sinkt 16 % der Körperhöhe → SLIDE
JUMP_RISE_FRACTION  = 0.07   # Nase steigt  7 % der Körperhöhe → JUMP
# Fallback in Pixeln, falls keine Körperhöhe kalibriert
SLIDE_DROP_FALLBACK = 110
JUMP_RISE_FALLBACK  = 55


DEFAULT_REFERENCE = {
    "left_ratio": 1/3,
    "right_ratio": 2/3,
    "crouch_threshold": 60,
    "jump_height_ratio": 0.75,
    "nose_y": None,
    "body_height": None,
}


def visible(kpt: Any) -> bool:
    """True, wenn YOLO den Keypoint [x, y, Konfidenz] wirklich erkannt hat."""
    return float(kpt[2]) >= KPT_CONF


def _mean_visible_y(person_kpts: Any, indices: Tuple[int, ...]) -> Optional[float]:
    ys = [float(person_kpts[i][1]) for i in indices if visible(person_kpts[i])]
    return sum(ys) / len(ys) if ys else None


def measure_body_height(person_kpts: Any) -> Tuple[Optional[float], str]:
    """Körperhöhe im Stand (Nase→Knöchel) in Pixeln und woher der Wert stammt.

    Sind die Knöchel nicht sichtbar (Füße nicht im Bild), wird sie aus der
    Rumpflänge geschätzt. (None, Grund), wenn auch das nicht geht.
    """
    nase = person_kpts[0]
    if not visible(nase):
        return None, "Nase nicht sichtbar"

    knoechel_y = _mean_visible_y(person_kpts, (15, 16))
    if knoechel_y is not None and knoechel_y > float(nase[1]):
        return knoechel_y - float(nase[1]), "aus Knöcheln"

    schulter_y = _mean_visible_y(person_kpts, (5, 6))
    huefte_y = _mean_visible_y(person_kpts, (11, 12))
    if schulter_y is not None and huefte_y is not None and huefte_y > schulter_y:
        return (huefte_y - schulter_y) * TORSO_TO_BODY, "aus Rumpflänge geschätzt, Füße nicht sichtbar"

    return None, "Knöchel und Rumpf nicht sichtbar"


def get_default_reference() -> Dict[str, float]:
    return DEFAULT_REFERENCE.copy()


def load_reference(filename: str = _REFERENCE_FILE) -> Dict[str, float]:
    """Gemeinsame Referenz für jeden Spieler laden (fehlende Werte → Defaults).

    Die Datei enthält nur feste Einstellungen (z.B. Spurgrenzen). Nasen- und
    Körperhöhe werden bei jeder Auswahl neu gemessen und nicht gespeichert.
    """
    reference = get_default_reference()
    path = Path(filename)
    if not path.exists():
        return reference
    try:
        with path.open("r", encoding="utf-8") as reference_file:
            data = json.load(reference_file)
    except (json.JSONDecodeError, OSError):
        return reference
    if isinstance(data, dict):
        reference.update(data)
    return reference


def extract_persons(results) -> List[TrackedPerson]:
    """Alle erkannten Personen als (Index, Keypoints, Hüfte x, Hüfte y).

    Keypoints sind ein Array 17 × [x, y, Konfidenz] (einmal pro Frame von der
    GPU geholt). Die Hüftmitte dient als Ankerpunkt für die Verfolgung – auch
    geschätzt (z.B. verdeckt) ist sie dafür gut genug.
    """
    persons: List[TrackedPerson] = []
    keypoints = results[0].keypoints
    if keypoints is None or len(keypoints.data) == 0:
        return persons

    data = keypoints.data
    data = data.cpu().numpy() if hasattr(data, "cpu") else np.asarray(data)
    if data.shape[-1] == 2:
        # Modell ohne Konfidenz-Werte → alle Punkte als sichtbar behandeln
        data = np.concatenate([data, np.ones(data.shape[:-1] + (1,), dtype=data.dtype)], axis=-1)

    for idx, person_kpts in enumerate(data):
        if len(person_kpts) < 17:
            continue
        huefte_x = float((person_kpts[11][0] + person_kpts[12][0]) / 2)
        huefte_y = float((person_kpts[11][1] + person_kpts[12][1]) / 2)
        persons.append((idx, person_kpts, huefte_x, huefte_y))
    return persons


def draw_person_indices(annotated: Any, persons: List[TrackedPerson]) -> None:
    for idx, _, huefte_x, huefte_y in persons:
        cv2.putText(
            annotated,
            str(idx),
            (int(huefte_x), int(huefte_y) - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            3,
        )


def draw_selection_prompt(annotated: Any, h: int, persons: List[TrackedPerson], line: int = 0) -> None:
    # cv2.putText kann keine Umlaute darstellen
    if persons:
        text = f"Linken Arm heben oder Taste 0-{len(persons) - 1}: mitspielen"
    else:
        text = "Keine Spieler erkannt. Warte auf Personen..."
    cv2.putText(
        annotated,
        text,
        (10, h - 20 - 30 * line),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2,
    )


def select_person_by_key(key: int, persons: List[TrackedPerson]) -> Optional[TrackedPerson]:
    if 48 <= key <= 57:
        sel = key - 48
        return next((p for p in persons if p[0] == sel), None)
    return None


def find_best_person(persons: List[TrackedPerson], selected_position: Tuple[float, float],
                     max_dist: float) -> Optional[Tuple[Any, float, float]]:
    """Person, deren Hüfte der letzten Spielerposition am nächsten ist.

    Liegt sie weiter als `max_dist` Pixel weg, wird None geliefert – sonst
    würde bei einem kurzen Erkennungsaussetzer eine andere Person (z.B. der
    Voice-Spieler) die Steuerung übernehmen.
    Ausnahme: Ist nur EINE Person im Bild, wird sie immer genommen. So findet
    die Verfolgung den Spieler nach einem Aussetzer sofort wieder, auch wenn er
    sich inzwischen weit bewegt hat (z.B. einen Spurwechsel gemacht hat).
    """
    if len(persons) == 1:
        _, person_kpts, huefte_x, huefte_y = persons[0]
        return person_kpts, huefte_x, huefte_y

    best_person = None
    min_dist_sq = max_dist ** 2
    for _, person_kpts, huefte_x, huefte_y in persons:
        dist_sq = (huefte_x - selected_position[0]) ** 2 + (huefte_y - selected_position[1]) ** 2
        if dist_sq <= min_dist_sq:
            min_dist_sq = dist_sq
            best_person = (person_kpts, huefte_x, huefte_y)
    return best_person


_LANE_NAME = {"LINKS": "left", "MITTE": "center", "RECHTS": "right"}


class LaneSender:
    """Sendet die Spur bei Änderung sofort, sonst alle `repeat_s` Sekunden erneut.

    Die Wiederholung hält das Spiel nach Pausen o.ä. synchron, ohne wie früher
    in jedem Frame zu senden und zu printen. `prefix` ist der OSC-Namespace des
    Spielers (/game/vision, beim zweiten Kamera-Spieler /game/vision2).
    """

    def __init__(self, client: SimpleUDPClient, prefix: str = "/game/vision", repeat_s: float = 0.25):
        self.client = client
        self.prefix = prefix
        self.repeat_s = repeat_s
        self._last: Optional[str] = None
        self._last_t = 0.0

    def send(self, target: str) -> None:
        now = time.monotonic()
        changed = target != self._last
        if changed or now - self._last_t >= self.repeat_s:
            addr = f"{self.prefix}/{_LANE_NAME[target]}"
            self.client.send_message(addr, [])
            if changed:
                print(addr)
            self._last = target
            self._last_t = now

    def reset(self) -> None:
        self._last = None


class ActionSender:
    """Meldet Sprung und Ducken: jump einmal, slide beim Abtauchen und danach alle
    `repeat_s` Sekunden erneut, solange der Spieler unten bleibt, stand beim
    Aufstehen. Das Spiel lässt die Figur so lange rutschen (mindestens 1,5 s) –
    geht ein stand verloren, endet das Rutschen dort trotzdem kurz darauf.
    """

    _ADDR = {"JUMP": "jump", "SLIDE": "slide", "STEHT": "stand"}

    def __init__(self, client: SimpleUDPClient, prefix: str = "/game/vision", repeat_s: float = 0.25):
        self.client = client
        self.prefix = prefix
        self.repeat_s = repeat_s
        self._state = "STEHT"
        self._last_t = 0.0

    def update(self, zustand: str) -> None:
        now = time.monotonic()
        if zustand != self._state:
            addr = f"{self.prefix}/{self._ADDR[zustand]}"
            self.client.send_message(addr, [])
            print(addr)
            self._state, self._last_t = zustand, now
        elif zustand == "SLIDE" and now - self._last_t >= self.repeat_s:
            self.client.send_message(f"{self.prefix}/slide", [])
            self._last_t = now

    def reset(self) -> None:
        self._state = "STEHT"


class LostSender:
    """Meldet dem Spiel, ob der Spieler gerade nicht erkannt wird (<prefix>/lost 1|0).

    Das Spiel hält an, solange die Meldung „verloren" frisch ist – deshalb wird
    sie alle `repeat_s` Sekunden wiederholt. Stürzt das Tracking ab, läuft das
    Spiel nach kurzer Zeit von selbst weiter, statt ewig zu warten.
    """

    def __init__(self, client: SimpleUDPClient, prefix: str = "/game/vision", repeat_s: float = 0.5):
        self.client = client
        self.prefix = prefix
        self.repeat_s = repeat_s
        self._lost = False
        self._last_t = 0.0

    def send(self, lost: bool) -> None:
        now = time.monotonic()
        changed = lost != self._lost
        if changed or (lost and now - self._last_t >= self.repeat_s):
            self.client.send_message(f"{self.prefix}/lost", [1 if lost else 0])
            if changed:
                print(f"{self.prefix}/lost {1 if lost else 0}")
            self._lost = lost
            self._last_t = now


def analyze_person(person_kpts: Any, w: int, lane_sender: LaneSender, action_sender: ActionSender,
                   reference: Optional[Dict[str, float]] = None, last_zustand: str = "STEHT",
                   zone: Tuple[float, float] = (0.0, 1.0)) -> Tuple[str, str]:
    """Spur, Sprung und Ducken eines Spielers bestimmen und ans Spiel melden.

    `zone` ist sein Bildbereich als Anteil der Breite: (0, 1) = ganzes Bild,
    im 2-Spieler-Modus die linke oder rechte Hälfte – dort liegen seine 3 Spuren.
    """
    reference = reference or get_default_reference()
    left_ratio = reference.get("left_ratio", 1/3)
    right_ratio = reference.get("right_ratio", 2/3)

    nase = person_kpts[0]
    nase_sichtbar = visible(nase)

    # Spur nach der Nase. Ist sie nicht sichtbar (z.B. Arme vor dem Gesicht),
    # nach der Hüftmitte – die liegt bei aufrechter Haltung genau darunter.
    if nase_sichtbar:
        x = float(nase[0])
    else:
        x = float((person_kpts[11][0] + person_kpts[12][0]) / 2)
    x0, zone_w = w * zone[0], w * (zone[1] - zone[0])
    if x < x0 + zone_w * left_ratio:
        target = "LINKS"
    elif x < x0 + zone_w * right_ratio:
        target = "MITTE"
    else:
        target = "RECHTS"
    lane_sender.send(target)

    # Ohne sichtbare Nase keine Aussage über Sprung/Ducken möglich →
    # Zustand beibehalten (sonst würde danach dieselbe Geste erneut ausgelöst)
    reference_nose_y = reference.get("nose_y")
    if not nase_sichtbar or reference_nose_y is None:
        action_sender.update(last_zustand)
        return target, last_zustand

    nose_y_current = float(nase[1])

    # Schwellen relativ zur kalibrierten Körperhöhe → auflösungs- und
    # abstandsunabhängig. Fallback auf feste Pixel, falls keine Höhe.
    body_h = reference.get("body_height")
    if body_h and body_h > 0:
        slide_drop = body_h * SLIDE_DROP_FRACTION
        jump_rise  = body_h * JUMP_RISE_FRACTION
    else:
        slide_drop = SLIDE_DROP_FALLBACK
        jump_rise  = JUMP_RISE_FALLBACK

    # Slide: Nase sinkt (nose_y wird größer)
    if nose_y_current >= reference_nose_y + slide_drop:
        zustand = "SLIDE"
    # Jump: Nase steigt (nose_y wird kleiner)
    elif nose_y_current <= reference_nose_y - jump_rise:
        zustand = "JUMP"
    else:
        zustand = "STEHT"

    # jump/slide/stand bei Änderung, slide wiederholt, solange geduckt
    action_sender.update(zustand)
    return target, zustand


def draw_player_status(annotated: Any, huefte_x: float, huefte_y: float, position: str, zustand: str,
                       label: str = "", color: Tuple[int, int, int] = (0, 255, 255)) -> None:
    text = f"{label + ' ' if label else ''}{position} | {zustand}"
    cv2.putText(
        annotated,
        text,
        (int(huefte_x) - 80, int(huefte_y) - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
    )


def draw_tracking_help(annotated: Any, h: int, text: str = "R = Auswahlmodus | Q = Beenden") -> None:
    cv2.putText(
        annotated,
        text,
        (10, h - 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )


def draw_zones(annotated: Any, zones: List[Tuple[float, float]], labels: List[str],
               colors: List[Tuple[int, int, int]], reference: Optional[Dict[str, float]] = None) -> None:
    """Spurgrenzen jeder Zone als dünne Linien, im 2-Spieler-Modus dazu die
    Trennlinie zwischen den Bildhälften und P1/P2 oben in der jeweiligen Farbe."""
    h, w = annotated.shape[:2]
    reference = reference or DEFAULT_REFERENCE
    for (z0, z1), label, col in zip(zones, labels, colors):
        x0, zw = w * z0, w * (z1 - z0)
        for ratio in (reference.get("left_ratio", 1/3), reference.get("right_ratio", 2/3)):
            x = int(x0 + zw * ratio)
            cv2.line(annotated, (x, h // 3), (x, h), (120, 120, 120), 1)
        if label:
            cv2.putText(annotated, label, (int(x0 + zw / 2) - 20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, col, 3)
    if len(zones) > 1:
        for z0, _ in zones[1:]:
            cv2.line(annotated, (int(w * z0), 0), (int(w * z0), h), (255, 255, 255), 2)


def draw_selected_player(annotated: Any, selected_person: Optional[int], h: int) -> None:
    if selected_person is not None:
        cv2.putText(
            annotated,
            f"Verfolge Spieler: {selected_person}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 128),
            2,
        )


def draw_player_lost(annotated: Any, h: int, lost_for: float,
                     takeover_hold_s: Optional[float] = None, label: str = "", line: int = 0) -> None:
    """Hinweis „Spieler verloren"; mit `takeover_hold_s` zusätzlich, wie ein neuer Spieler übernimmt.
    `line` schiebt die Zeilen nach oben (zweiter Spieler)."""
    # Hinweis: cv2.putText kann keine Umlaute darstellen
    who = label or "Spieler"
    y = h - 20 - 100 * line
    cv2.putText(
        annotated,
        f"{who} verloren ({lost_for:.0f} s) - warte auf dieselbe Person ... (R = Auswahlmodus)",
        (10, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2,
    )
    if takeover_hold_s is not None:
        cv2.putText(
            annotated,
            f"Neuer Spieler{' fuer ' + label if label else ''}? Linken Arm {takeover_hold_s:.0f} s oben halten",
            (10, y - 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 165, 255),
            2,
        )


def draw_perf(annotated: Any, w: int, fps: float, infer_ms: float, device: str) -> None:
    cv2.putText(
        annotated,
        f"{fps:4.1f} FPS | YOLO {infer_ms:4.1f} ms | {device}",
        (w - 430, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
    )


def draw_countdown(annotated: Any, remaining: float, h: int, w: int, cx: Optional[int] = None,
                   color: Tuple[int, int, int] = (0, 255, 255)) -> None:
    """Countdown vor der Kalibrierung groß zeichnen – in der Bildmitte oder bei `cx`."""
    cx = w // 2 if cx is None else cx
    cv2.putText(annotated, "Gerade hinstellen!", (cx - 220, h // 2 - 90),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 3)
    cv2.putText(annotated, str(int(remaining) + 1), (cx - 40, h // 2 + 60),
                cv2.FONT_HERSHEY_SIMPLEX, 5.0, color, 10)


# YOLO-Keypoint-Indizes: 5/6 = linke/rechte Schulter, 9/10 = linkes/rechtes Handgelenk.
# "links"/"rechts" ist die YOLO-Bezeichnung im (gespiegelten) Kamerabild.
_WRIST_SHOULDER = {"left": (9, 5), "right": (10, 6)}


def wrist_raised(person_kpts: Any, side: str, body_height: Optional[float] = None, pixel_thresh: int = 30) -> bool:
    """True, wenn das Handgelenk `side` ("left"/"right") deutlich über der Schulter ist.

    Mit `body_height` gilt eine relative Schwelle (10 % der Körperhöhe),
    sonst `pixel_thresh` als Fallback.
    """
    wrist_idx, shoulder_idx = _WRIST_SHOULDER[side]
    wrist = person_kpts[wrist_idx]
    shoulder = person_kpts[shoulder_idx]

    # Nur wirklich erkannte Punkte zählen – geschätzte Positionen (z.B. Hand
    # außerhalb des Bildes) dürfen keine Geste auslösen
    if not (visible(wrist) and visible(shoulder)):
        return False

    thresh = body_height * 0.10 if body_height and body_height > 0 else pixel_thresh

    # Pixel-y wächst nach unten → gehoben = kleineres y
    return float(wrist[1]) < float(shoulder[1]) - thresh

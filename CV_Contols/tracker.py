import cv2
import json
from pathlib import Path
from pythonosc.udp_client import SimpleUDPClient
from typing import Any, Dict, List, Optional, Tuple

TrackedPerson = Tuple[int, Any, float, float]


# ── Zustandsschwellen ─────────────────────────────────────────────────
# Anteil der kalibrierten Körperhöhe (Nase→Knöchel). Dadurch auflösungs-
# und abstandsunabhängig — egal welche Kameraauflösung oder wie weit weg.
SLIDE_DROP_FRACTION = 0.16   # Nase sinkt 16 % der Körperhöhe → SLIDE
JUMP_RISE_FRACTION  = 0.07   # Nase steigt  7 % der Körperhöhe → JUMP
# Fallback in Pixeln, falls keine Körperhöhe kalibriert (Knöchel nicht sichtbar)
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


def measure_body_height(person_kpts: Any) -> Optional[float]:
    """Vertikaler Abstand Nase→Knöchel in Pixeln (Körperhöhe im Stand).
    Liefert None, wenn Nase oder beide Knöchel nicht erkannt wurden.
    """
    nase = person_kpts[0]
    li_knoechel = person_kpts[15]
    re_knoechel = person_kpts[16]
    knoechel_ys = [float(a[1]) for a in (li_knoechel, re_knoechel) if a[1] > 0]
    if nase[1] <= 0 or not knoechel_ys:
        return None
    knoechel_y = sum(knoechel_ys) / len(knoechel_ys)
    hoehe = knoechel_y - float(nase[1])
    return hoehe if hoehe > 0 else None


def get_default_reference() -> Dict[str, float]:
    return DEFAULT_REFERENCE.copy()


def load_player_reference(player_id: int, filename: str = "player_references.json") -> Dict[str, float]:
    path = Path(filename)
    if not path.exists():
        return get_default_reference()

    try:
        with path.open("r", encoding="utf-8") as reference_file:
            data = json.load(reference_file)
    except (json.JSONDecodeError, OSError):
        return get_default_reference()

    return data.get(str(player_id), get_default_reference())


def save_player_reference(player_id: int, reference: Dict[str, float], filename: str = "player_references.json") -> None:
    path = Path(filename)
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as reference_file:
                data = json.load(reference_file)
        else:
            data = {}
        
        data[str(player_id)] = reference
        
        with path.open("w", encoding="utf-8") as reference_file:
            json.dump(data, reference_file, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Fehler beim Speichern der Referenz: {e}")


def extract_persons(results) -> List[TrackedPerson]:
    persons: List[TrackedPerson] = []
    if results[0].keypoints is None or len(results[0].keypoints.xy) == 0:
        return persons

    for idx, person_kpts in enumerate(results[0].keypoints.xy):
        if len(person_kpts) < 17:
            continue

        li_huefte = person_kpts[11]
        re_huefte = person_kpts[12]
        if li_huefte[0] <= 0 or re_huefte[0] <= 0:
            continue

        huefte_x = float((li_huefte[0] + re_huefte[0]) / 2)
        huefte_y = float((li_huefte[1] + re_huefte[1]) / 2)
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


def draw_selection_prompt(annotated: Any, h: int, persons: List[TrackedPerson]) -> None:
    if persons:
        text = f"Wähle Spieler 0-{len(persons) - 1} mit Taste"
    else:
        text = "Keine Spieler erkannt. Warte auf Personen..."
    cv2.putText(
        annotated,
        text,
        (10, h - 20),
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


def find_best_person(persons: List[TrackedPerson], selected_position: Tuple[float, float]) -> Optional[Tuple[Any, float, float]]:
    best_person = None
    min_dist = float("inf")
    for _, person_kpts, huefte_x, huefte_y in persons:
        dist = (huefte_x - selected_position[0]) ** 2 + (huefte_y - selected_position[1]) ** 2
        if dist < min_dist:
            min_dist = dist
            best_person = (person_kpts, huefte_x, huefte_y)
    return best_person


def analyze_person(person_kpts: Any, h: int, w: int, client: SimpleUDPClient, position: str, reference: Optional[Dict[str, float]] = None, last_zustand: str = "STEHT") -> Tuple[str, str]:
    reference = reference or get_default_reference()
    left_ratio = reference.get("left_ratio", 1/3)
    right_ratio = reference.get("right_ratio", 2/3)
    crouch_threshold = reference.get("crouch_threshold", 60)
    jump_height_ratio = reference.get("jump_height_ratio", 0.75)

    li_huefte = person_kpts[11]
    re_huefte = person_kpts[12]
    li_knie = person_kpts[13]
    re_knie = person_kpts[14]
    li_knoechel = person_kpts[15]
    re_knoechel = person_kpts[16]

    huefte_x = float((li_huefte[0] + re_huefte[0]) / 2)
    huefte_y = float((li_huefte[1] + re_huefte[1]) / 2)

    # Nasenhöhe auslesen
    nase = person_kpts[0]
    reference_nose_y = reference.get("nose_y")
    jump_tolerance = reference.get("jump_tolerance", 30)
    slide_tolerance = reference.get("slide_tolerance", 30)

    # Neue Logik zur Positionserkennung basierend auf Nase
    if nase[0] < w * left_ratio:
        client.send_message("/game/vision/left", [])
        print("/game/vision/left")
        target = "LINKS"
    elif nase[0] < w * right_ratio:
        client.send_message("/game/vision/center", [])
        print("/game/vision/center")
        target = "MITTE"
    else:
        client.send_message("/game/vision/right", [])
        print("/game/vision/right")
        target = "RECHTS"
    
    zustand = "STEHT"

    # Nasenhöhe-basierte Zustandserkennung
    if nase[1] > 0 and reference_nose_y is not None:
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
        # Sonst: STEHT
        else:
            zustand = "STEHT"
        
        # Nachricht nur senden, wenn Zustand sich ändert
        if zustand != last_zustand:
            if zustand == "JUMP":
                client.send_message("/game/vision/jump", [])
                print("/game/vision/jump")
            elif zustand == "SLIDE":
                client.send_message("/game/vision/slide", [])
                print("/game/vision/slide")
            else:
                #client.send_message("/game/vision/stand", [])
                print("/game/vision/stand")
    

    return target, zustand


def draw_player_status(annotated: Any, huefte_x: float, huefte_y: float, position: str, zustand: str) -> None:
    text = f"{position} | {zustand}"
    cv2.putText(
        annotated,
        text,
        (int(huefte_x) - 80, int(huefte_y) - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )


def draw_tracking_help(annotated: Any, h: int) -> None:
    cv2.putText(
        annotated,
        "R = Auswahlmodus | Q = Beenden",
        (10, h - 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )


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


def draw_no_person(annotated: Any, h: int) -> None:
    cv2.putText(
        annotated,
        "Keine Person erkannt. Bitte r drücken, um erneut zu wählen.",
        (10, h - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2,
    )


def left_arm_raised(person_kpts: Any, body_height: Optional[float] = None, pixel_thresh: int = 30) -> bool:
    """Erkennt ob beide Arme oberhalb der Schultern sind.

    Uses keypoint indices: 5=left_shoulder, 6=right_shoulder, 9=left_wrist, 10=right_wrist.
    Wenn `body_height` gegeben, wird eine relative Schwelle genutzt (10% der Körperhöhe),
    sonst `pixel_thresh` als Fallback.
    """
    # Indices: 5 left shoulder, 6 right shoulder, 9 left wrist, 10 right wrist
    try:
        li_sh = person_kpts[5]
        re_sh = person_kpts[6]
        li_wr = person_kpts[9]
        re_wr = person_kpts[10]
    except Exception:
        return False

    # Sicherstellen, dass Keypoints vorhanden sind
    if li_sh[1] <= 0 or re_sh[1] <= 0 or li_wr[1] <= 0 or re_wr[1] <= 0:
        return False

    if body_height and body_height > 0:
        thresh = body_height * 0.10
    else:
        thresh = pixel_thresh

    # y-Werte in den Keypoints sind Pixelpositionen (größer = weiter unten).
    # Arm gehoben = Hand (wrist) deutlich oberhalb Schulter (smaller y).
    right_raised = float(re_wr[1]) < float(re_sh[1]) - thresh

    return right_raised

def right_arm_raised(person_kpts: Any, body_height: Optional[float] = None, pixel_thresh: int = 30) -> bool:
    """Erkennt ob beide Arme oberhalb der Schultern sind.

    Uses keypoint indices: 5=left_shoulder, 6=right_shoulder, 9=left_wrist, 10=right_wrist.
    Wenn `body_height` gegeben, wird eine relative Schwelle genutzt (10% der Körperhöhe),
    sonst `pixel_thresh` als Fallback.
    """
    # Indices: 5 left shoulder, 6 right shoulder, 9 left wrist, 10 right wrist
    try:
        li_sh = person_kpts[5]
        re_sh = person_kpts[6]
        li_wr = person_kpts[9]
        re_wr = person_kpts[10]
    except Exception:
        return False

    # Sicherstellen, dass Keypoints vorhanden sind
    if li_sh[1] <= 0 or re_sh[1] <= 0 or li_wr[1] <= 0 or re_wr[1] <= 0:
        return False

    if body_height and body_height > 0:
        thresh = body_height * 0.10
    else:
        thresh = pixel_thresh

    # y-Werte in den Keypoints sind Pixelpositionen (größer = weiter unten).
    # Arm gehoben = Hand (wrist) deutlich oberhalb Schulter (smaller y).
    left_raised = float(li_wr[1]) < float(li_sh[1]) - thresh

    return left_raised

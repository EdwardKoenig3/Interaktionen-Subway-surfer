from turtle import position

import cv2
import json
from pathlib import Path
from pythonosc.udp_client import SimpleUDPClient
from typing import Any, Dict, List, Optional, Tuple

TrackedPerson = Tuple[int, Any, float, float]


DEFAULT_REFERENCE = {
    "left_ratio": 1/3,
    "right_ratio": 2/3,
    "crouch_threshold": 60,
    "jump_height_ratio": 0.75,
    "nose_y": None,
}


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

    # Alte Logik zur Positionserkennung basierend auf Hüfte
    # if huefte_x < w * left_ratio:
    #     target = "LINKS"
    #     if position != target:
    #         client.send_message("/game/left", [])
    #         print("/game/left")
    # elif huefte_x < w * right_ratio:
    #     target = "MITTE"
    #     if position != target:
    #         client.send_message("/game/center", [])
    #         print("/game/center")
    # else:
    #     target = "RECHTS"
    #     if position != target:
    #         client.send_message("/game/right", [])
    #         print("/game/right")

    # Neue Logik zur Positionserkennung basierend auf Nase
    if nase[0] < w * left_ratio:
        client.send_message("/game/left", [])
        print("/game/left")
        target = "LINKS"
    elif nase[0] < w * right_ratio:
        client.send_message("/game/center", [])
        print("/game/center")
        target = "MITTE"
    else:
        client.send_message("/game/right", [])
        print("/game/right")
        target = "RECHTS"
    
    zustand = "STEHT"
    
    # Nasenhöhe-basierte Zustandserkennung
    if nase[1] > 0 and reference_nose_y is not None:
        nose_y_current = float(nase[1])
        
        # Slide: wenn Nase >= 200px niedriger als Referenz (größer wird)
        if nose_y_current >= reference_nose_y + 250:
            zustand = "SLIDE"

        # Jump: wenn Nase <= 150px höher als Referenz (kleiner wird)
        elif nose_y_current <= reference_nose_y - 100:
            zustand = "JUMP"
        # Sonst: STEHT
        else:
            zustand = "STEHT"
        
        # Nachricht nur senden, wenn Zustand sich ändert
        if zustand != last_zustand:
            if zustand == "JUMP":
                client.send_message("/game/jump", [])
                print("/game/jump")
            elif zustand == "SLIDE":
                client.send_message("/game/slide", [])
                print("/game/slide")
            else:
                #client.send_message("/game/stand", [])
                print("/game/stand")
    
    # Fallback Slide-Erkennung basierend auf Knie (alte Logik)
    #if zustand == "STEHT" and (li_knie[1] > 0 and re_knie[1] > 0 and li_huefte[1] > 0 and re_huefte[1] > 0):
    #    knie_y = (li_knie[1] + re_knie[1]) / 2
    #    huefte_y = (li_huefte[1] + re_huefte[1]) / 2
    #    if abs(huefte_y - knie_y) < crouch_threshold:
    #        zustand = "SLIDE"
    #        if zustand != last_zustand:
    #            client.send_message("/game/slide", [])
    #            print("/game/slide")

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

"""
poses.py – Körperhaltungen, die Power-ups auslösen.

    Hände vor der Brust (oder Arme kreuzen)  → shield   SCHILD
    Arme seitlich ausbreiten (T-Pose)        → glide    GLEITEN
    Hände in die Hüften                      → magnet   MAGNET

Eine Haltung zählt erst, wenn sie POSE_HOLD_S lang gehalten wird – kurzes
Armeschwingen beim Springen löst nichts aus. Pro Halten wird nur einmal
ausgelöst; danach muss die Haltung erst aufgelöst werden. Die Abklingzeit
(Cooldown) verwaltet das Spiel und zeigt sie auch an.

Alle Maße sind relativ zur Schulterbreite – unabhängig von Abstand und
Auflösung. Bei keiner Haltung sind die Hände über den Schultern, sie stören
also weder Auswahl (linker Arm hoch), Abmelden (rechter Arm) noch Start (beide).
"""

from typing import Any, Optional, Tuple

import cv2
import numpy as np

from tracker import visible

POSE_HOLD_S = 0.5    # so lange halten, dann löst das Power-up aus
POSE_GAP_S  = 0.2    # kürzere Erkennungslücken beim Halten werden überbrückt

LABELS = {"shield": "SCHILD", "glide": "GLEITEN", "magnet": "MAGNET"}

# COCO-Keypoints je Körperseite: (Schulter, Ellbogen, Handgelenk, Hüfte)
_ARMS = ((5, 7, 9, 11), (6, 8, 10, 12))


def _p(kpts: Any, i: int) -> np.ndarray:
    return np.array([float(kpts[i][0]), float(kpts[i][1])])


def detect(person_kpts: Any) -> Optional[str]:
    """Power-up-Haltung, die die Person gerade einnimmt – oder None."""
    if not all(visible(person_kpts[i]) for i in (5, 6, 7, 8, 9, 10)):
        return None
    ls, rs = _p(person_kpts, 5), _p(person_kpts, 6)
    sw = float(np.linalg.norm(ls - rs))
    if sw < 10:                       # winzig oder ganz seitlich → nicht auswertbar
        return None
    cx, sy = (ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2
    if _is_glide(person_kpts, sw, cx, sy):
        return "glide"
    if _is_shield(person_kpts, sw, cx, sy):
        return "shield"
    if _is_magnet(person_kpts, sw, cx, sy):
        return "magnet"
    return None


def _is_glide(k: Any, sw: float, cx: float, sy: float) -> bool:
    """Arme waagrecht ausgestreckt: Ellbogen und Hände etwa auf Schulterhöhe,
    jeweils weiter außen als Schulter bzw. Ellbogen, Hände weit auseinander."""
    for s_i, e_i, w_i, _ in _ARMS:
        s, e, wr = _p(k, s_i), _p(k, e_i), _p(k, w_i)
        out = 1.0 if s[0] >= cx else -1.0         # "nach außen" für diesen Arm
        if abs(e[1] - sy) > 0.5 * sw or abs(wr[1] - sy) > 0.6 * sw:
            return False
        # Ellbogen klar außen, Hand nicht wieder nach innen (leicht gebeugt ist ok)
        if out * (e[0] - s[0]) < 0.3 * sw or out * (wr[0] - e[0]) < 0.1 * sw:
            return False
    return abs(_p(k, 9)[0] - _p(k, 10)[0]) > 2.6 * sw


def _is_shield(k: Any, sw: float, cx: float, sy: float) -> bool:
    """Beide Hände vor der Brust: auf Brusthöhe, nah beieinander und mittig vor dem
    Körper – zählt auch mit gekreuzten Armen. "Mittig" schließt Alltagshaltungen
    aus, bei denen beide Hände auf einer Seite sind (Jacke halten, zeigen) – dort
    liefert YOLO bei verdeckten Armen sonst oft genau so eine Handposition."""
    w1, w2 = _p(k, 9), _p(k, 10)
    for wr in (w1, w2):
        if not (sy - 0.2 * sw < wr[1] < sy + 0.9 * sw):
            return False
        if abs(wr[0] - cx) > 0.75 * sw:
            return False
    if abs((w1[0] + w2[0]) / 2 - cx) > 0.3 * sw:
        return False
    return abs(w1[0] - w2[0]) < 1.2 * sw and abs(w1[1] - w2[1]) < 0.6 * sw


def _is_magnet(k: Any, sw: float, cx: float, sy: float) -> bool:
    """Hände in die Hüften: Hand an der Taille (nicht tiefer als die Hüfte),
    Ellbogen deutlich nach außen und weiter außen als die Hand. Das unterscheidet
    es von locker hängenden Armen und von Händen in den Hosentaschen."""
    if not (visible(k[11]) and visible(k[12])):
        return False
    for s_i, e_i, w_i, h_i in _ARMS:
        s, e, wr, hp = _p(k, s_i), _p(k, e_i), _p(k, w_i), _p(k, h_i)
        out = 1.0 if s[0] >= cx else -1.0
        if wr[1] > hp[1] + 0.15 * sw or abs(wr[0] - hp[0]) > 0.45 * sw:
            return False                          # Hand nicht an der Taille
        if np.linalg.norm(wr - hp) > 0.6 * sw:
            return False
        if out * (e[0] - s[0]) < 0.3 * sw or out * (e[0] - wr[0]) < 0.2 * sw:
            return False                          # Ellbogen nicht deutlich außen
        if not (s[1] < e[1] < hp[1]):             # Ellbogen zwischen Schulter und Hüfte
            return False
    return True


class PoseTrigger:
    """Löst ein Power-up aus, sobald eine Haltung POSE_HOLD_S gehalten wurde –
    pro Halten nur einmal."""

    def __init__(self):
        self.pose: Optional[str] = None
        self._since = 0.0
        self._seen = 0.0
        self._fired = False

    def update(self, person_kpts: Any, now: float) -> Optional[str]:
        """Haltung in diesem Bild auswerten → Power-up, falls es jetzt auslöst."""
        pose = detect(person_kpts)
        if pose is not None:
            if pose != self.pose:
                self.pose, self._since, self._fired = pose, now, False
            self._seen = now
        elif self.pose is not None and now - self._seen > POSE_GAP_S:
            self.pose = None
        if self.pose is not None and not self._fired and now - self._since >= POSE_HOLD_S:
            self._fired = True
            return self.pose
        return None

    def progress(self, now: float) -> Optional[Tuple[str, float]]:
        """(Haltung, Anteil 0…1), solange eine gehalten wird und noch nicht ausgelöst hat."""
        if self.pose is None or self._fired:
            return None
        return self.pose, min(1.0, (now - self._since) / POSE_HOLD_S)

    def reset(self) -> None:
        self.pose = None
        self._fired = False


def draw_progress(annotated: Any, x: float, y: float, pose: str, frac: float,
                  color: Tuple[int, int, int]) -> None:
    """Balken über dem Kopf, solange eine Power-up-Haltung gehalten wird."""
    x0, y0 = int(x) - 70, int(y) - 40
    cv2.putText(annotated, LABELS[pose], (x0, y0 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.rectangle(annotated, (x0, y0), (x0 + 140, y0 + 12), (80, 80, 80), -1)
    cv2.rectangle(annotated, (x0, y0), (x0 + int(140 * frac), y0 + 12), color, -1)

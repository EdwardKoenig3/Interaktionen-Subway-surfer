"""
identity.py – Wiedererkennung des gewählten Spielers an seiner Kleidung.

YOLO-Pose liefert nur, WO Personen sind – nicht, WER sie sind. Damit die
Steuerung nach einem Aussetzer (Spieler kurz aus dem Bild, verdeckt,
Bewegungsunschärfe beim Sprung) nicht auf eine andere Person springt, merkt
sich der Tracker beim Kalibrieren ein Farbprofil des Spielers:

  * Regionen aus den Keypoints: Brust, Bauch (Schultern→Hüfte), Ober- und
    Unterschenkel – so zählt fast nur die Kleidung, kaum Hintergrund.
  * Pro Region ein Farbhistogramm: Farbton × Sättigung für bunte Pixel, dazu
    4 Helligkeitsstufen für Schwarz/Grau/Weiß. Dadurch robust gegen
    Helligkeits- und Weißabgleich-Schwankungen der Kamera.
  * Ähnlichkeit = 1 − Hellinger-Abstand (1 = gleiche Farben), gewichtet über
    die Regionen, die bei beiden sichtbar sind.

Kosten: deutlich unter 1 ms pro Person auf der CPU, kein zweites Modell nötig.
Grenze: Zwei Personen in sehr ähnlicher Kleidung (z.B. beide schwarz) sind
kaum zu unterscheiden – dafür bräuchte es ein ReID- oder Gesichtsmodell.
"""

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from tracker import TrackedPerson, visible

Signature = Dict[str, np.ndarray]   # Region → normiertes Histogramm

# ── Schwellen (Ähnlichkeit 0…1) ───────────────────────────────────────
# Gemessen an Testbildern mit Helligkeit ±25 %, Weißabgleich, Unschärfe und
# Rauschen: dieselbe Person ≥ 0.72, andere Kleidung ≈ 0.3, zwei fast gleiche
# dunkle Anzüge ≈ 0.62. Bei Bedarf hier nachjustieren – die Werte stehen im
# Kamerabild neben jeder Person.
SIM_ACCEPT = 0.68     # ab hier gilt eine Person nach einem Verlust wieder als der Spieler
SIM_REJECT = 0.45     # darunter ist es sicher jemand anderes – auch direkt neben dem Spieler
SIM_MARGIN = 0.08     # so viel ähnlicher als alle anderen muss der Spieler sein
CONFIRM_FRAMES = 3    # so viele Bilder in Folge muss die Wiedererkennung passen
SHORT_GAP_S = 0.5     # kürzere Aussetzer werden noch über die Position überbrückt

MIN_SAMPLES = 5       # ab so vielen Bildern ist das Profil benutzbar
LEARN_SAMPLES = 45    # so viele Bilder fließen insgesamt ins Profil ein

# Gewichte der Regionen (werden über die sichtbaren Regionen normiert)
_REGION_WEIGHTS = {"brust": 0.25, "bauch": 0.25, "oberschenkel": 0.3, "unterschenkel": 0.2}
_MIN_PIXELS = 150     # kleinere Regionen sind zu verrauscht

# Histogramm: bunte Pixel nach Farbton (12) × Sättigung (3), unbunte/dunkle
# Pixel nach Helligkeit (4: schwarz … weiß)
_N_HUE, _N_SAT, _N_GRAY = 12, 3, 4
_S_MIN, _V_MIN = 50, 45
_N_BINS = _N_HUE * _N_SAT + _N_GRAY


def _pt(kpt: Any) -> np.ndarray:
    return np.array([float(kpt[0]), float(kpt[1])], np.float32)


def _regions(person_kpts: Any) -> Dict[str, List[Tuple[str, Any]]]:
    """Regionen als Zeichenanweisungen: ("poly", Punkte) oder ("line", (a, b, Dicke))."""
    out: Dict[str, List[Tuple[str, Any]]] = {}
    ls, rs, lh, rh = (person_kpts[i] for i in (5, 6, 11, 12))
    shoulders = visible(ls) and visible(rs)
    hips = visible(lh) and visible(rh)

    if shoulders:
        if hips:
            quad = np.array([_pt(ls), _pt(rs), _pt(rh), _pt(lh)])
        else:
            # Hüfte nicht im Bild (Person nah an der Kamera): Rumpf ≈ 1,1 × Schulterbreite
            down = np.array([0.0, float(np.linalg.norm(_pt(ls) - _pt(rs))) * 1.1], np.float32)
            quad = np.array([_pt(ls), _pt(rs), _pt(rs) + down, _pt(ls) + down])
        # Auf 75 % schrumpfen → Arme und Hintergrund am Rand fallen weg
        center = quad.mean(axis=0)
        quad = center + (quad - center) * 0.75
        mid_l, mid_r = (quad[0] + quad[3]) / 2, (quad[1] + quad[2]) / 2
        out["brust"] = [("poly", np.array([quad[0], quad[1], mid_r, mid_l]))]
        out["bauch"] = [("poly", np.array([mid_l, mid_r, quad[2], quad[3]]))]

    # Beine als dicke Linien Hüfte→Knie→Knöchel, Dicke relativ zur Hüftbreite
    if hips:
        ref_w = float(np.linalg.norm(_pt(lh) - _pt(rh)))
    elif shoulders:
        ref_w = float(np.linalg.norm(_pt(ls) - _pt(rs))) * 0.8
    else:
        return out
    thickness = max(3, int(ref_w * 0.45))
    for name, segments in (("oberschenkel", ((11, 13), (12, 14))),
                           ("unterschenkel", ((13, 15), (14, 16)))):
        lines = [("line", (_pt(person_kpts[a]), _pt(person_kpts[b]), thickness))
                 for a, b in segments if visible(person_kpts[a]) and visible(person_kpts[b])]
        if lines:
            out[name] = lines
    return out


def _histogram(hsv_pixels: np.ndarray) -> np.ndarray:
    h = hsv_pixels[:, 0].astype(np.int32)
    s = hsv_pixels[:, 1].astype(np.int32)
    v = hsv_pixels[:, 2].astype(np.int32)
    bunt = (s >= _S_MIN) & (v >= _V_MIN)
    idx = np.where(
        bunt,
        np.minimum(h * _N_HUE // 180, _N_HUE - 1) * _N_SAT
        + np.minimum((s - _S_MIN) * _N_SAT // (256 - _S_MIN), _N_SAT - 1),
        _N_HUE * _N_SAT + np.minimum(v * _N_GRAY // 256, _N_GRAY - 1),
    )
    hist = np.bincount(idx, minlength=_N_BINS).astype(np.float32)
    return hist / hist.sum()


def appearance(frame: Any, person_kpts: Any) -> Signature:
    """Farbprofil einer Person: Region → Histogramm (nicht sichtbare Regionen fehlen)."""
    regions = _regions(person_kpts)
    if not regions:
        return {}

    # Nur den Bildausschnitt um die Regionen umrechnen, nicht das ganze Bild
    pts = []
    for items in regions.values():
        for kind, data in items:
            pts.extend(data if kind == "poly" else data[:2])
    pts = np.array(pts)
    pad = 2 + max((data[2] for items in regions.values() for kind, data in items if kind == "line"), default=0)
    h, w = frame.shape[:2]
    x0, y0 = np.maximum(np.floor(pts.min(axis=0)) - pad, 0).astype(int)
    x1, y1 = np.minimum(np.ceil(pts.max(axis=0)) + pad, [w, h]).astype(int)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return {}
    roi = frame[y0:y1, x0:x1]
    # Für Farbhistogramme reicht halbe Auflösung (spart ~3/4 der Rechenzeit)
    scale = 0.5 if y1 - y0 > 160 else 1.0
    if scale != 1.0:
        roi = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    offset = np.array([x0, y0], np.float32)

    def to_roi(p):
        return np.round((p - offset) * scale).astype(np.int32)

    sig: Signature = {}
    for name, items in regions.items():
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for kind, data in items:
            if kind == "poly":
                cv2.fillConvexPoly(mask, to_roi(data), 255)
            else:
                a, b, thickness = data
                cv2.line(mask, tuple(int(v) for v in to_roi(a)), tuple(int(v) for v in to_roi(b)),
                         255, max(1, int(thickness * scale)))
        pixels = hsv[mask > 0]
        if len(pixels) >= _MIN_PIXELS:
            sig[name] = _histogram(pixels)
    return sig


def similarity(a: Signature, b: Signature) -> Optional[float]:
    """1 = gleiche Kleidungsfarben, 0 = keine Überschneidung. None ohne gemeinsame Region."""
    num = den = 0.0
    for name, weight in _REGION_WEIGHTS.items():
        if name in a and name in b:
            bc = float(np.sum(np.sqrt(a[name] * b[name])))   # Bhattacharyya-Koeffizient
            num += weight * (1.0 - np.sqrt(max(0.0, 1.0 - bc)))
            den += weight
    return num / den if den else None


def overlaps_other(player_kpts: Any, persons: List[TrackedPerson]) -> bool:
    """True, wenn sich eine andere Person im Bild mit dem Spieler überdeckt (Hüften
    näher als eine Schulterbreite) – dann würden sich beim Lernen die Farben mischen."""
    ls, rs = player_kpts[5], player_kpts[6]
    width = float(np.linalg.norm(_pt(ls) - _pt(rs))) if visible(ls) and visible(rs) else 100.0
    hip = (_pt(player_kpts[11]) + _pt(player_kpts[12])) / 2
    return any(kpts is not player_kpts and np.hypot(hx - hip[0], hy - hip[1]) < width
               for _, kpts, hx, hy in persons)


def draw_similarities(annotated: Any, persons: List[TrackedPerson], sims: List[Optional[float]]) -> None:
    """Ähnlichkeit zum gelernten Spieler unter jede Person schreiben.
    Grün = wird wiedererkannt, gelb = unsicher, rot = sicher jemand anderes."""
    for (_, _, huefte_x, huefte_y), sim in zip(persons, sims):
        if sim is None:
            text, col = "ID ?", (160, 160, 160)
        else:
            text = f"ID {sim:.2f}"
            col = (0, 220, 0) if sim >= SIM_ACCEPT else (0, 220, 255) if sim >= SIM_REJECT else (0, 0, 255)
        cv2.putText(annotated, text, (int(huefte_x) - 45, int(huefte_y) + 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)


class PlayerIdentity:
    """Gelerntes Farbprofil des Spielers – Mittel über die ersten LEARN_SAMPLES Bilder."""

    def __init__(self):
        self._sums: Dict[str, np.ndarray] = {}
        self._counts: Dict[str, int] = {}
        self.samples = 0
        self._reference: Optional[Signature] = None

    @property
    def ready(self) -> bool:
        return self.samples >= MIN_SAMPLES

    @property
    def complete(self) -> bool:
        return self.samples >= LEARN_SAMPLES

    def learn(self, sig: Signature) -> None:
        if not sig or self.complete:
            return
        for name, hist in sig.items():
            self._sums[name] = self._sums.get(name, 0) + hist
            self._counts[name] = self._counts.get(name, 0) + 1
        self.samples += 1
        self._reference = None

    def reference(self) -> Signature:
        if self._reference is None:
            # Nur Regionen, die oft genug sichtbar waren (sonst zu zufällig)
            min_count = max(MIN_SAMPLES, int(0.3 * self.samples))
            self._reference = {name: total / total.sum() for name, total in self._sums.items()
                               if self._counts[name] >= min_count}
        return self._reference

    def similarity(self, sig: Signature) -> Optional[float]:
        return similarity(self.reference(), sig) if self.ready else None


class PlayerLock:
    """Entscheidet pro Bild, welche Person der gewählte Spieler ist.

    Solange der Spieler sichtbar ist, wird er über die Position verfolgt
    (nächste Person im Suchradius); eindeutig anders gekleidete Personen
    (Ähnlichkeit < SIM_REJECT) werden dabei übergangen. Ist er länger als
    SHORT_GAP_S weg, kommt nur noch eine Person in Frage, die eindeutig wie der
    Spieler aussieht – egal wo sie steht und wie viele andere im Bild sind.
    """

    def __init__(self):
        self.identity = PlayerIdentity()
        self.sims: List[Optional[float]] = []   # Ähnlichkeit je Person im letzten Bild
        self._confirm = 0
        self._confirm_pos: Optional[Tuple[float, float]] = None

    def find(self, frame: Any, persons: List[TrackedPerson], last_pos: Tuple[float, float],
             max_dist: float, lost_for: Optional[float]) -> Optional[Tuple[Any, float, float]]:
        """Spieler (Keypoints, Hüfte x, Hüfte y) oder None.

        `lost_for`: None = im letzten Bild noch gefunden, sonst Sekunden seit dem Verlust.
        Erst benutzen, wenn `identity.ready` – vorher gibt es kein Profil.
        """
        self.sims = [self.identity.similarity(appearance(frame, kpts)) for _, kpts, _, _ in persons]

        if lost_for is None or lost_for < SHORT_GAP_S:
            self._confirm, self._confirm_pos = 0, None
            return self._by_position(persons, last_pos, max_dist, continuing=lost_for is None)
        return self._by_identity(persons, max_dist)

    def _by_position(self, persons, last_pos, max_dist, continuing):
        candidates = []
        for i, (_, _, hx, hy) in enumerate(persons):
            sim = self.sims[i]
            dist = float(np.hypot(hx - last_pos[0], hy - last_pos[1]))
            # Ohne messbares Aussehen (z.B. Schultern unscharf) zählt nur, wer
            # direkt an den Spieler aus dem letzten Bild anschließt
            if dist <= max_dist and (sim >= SIM_REJECT if sim is not None else continuing):
                candidates.append((dist, i))
        if not candidates:
            return None
        candidates.sort()
        # Mehrere Personen dicht beieinander: Wiedererkannte schlagen solche, die
        # nur näher stehen. Passen mehrere etwa gleich gut → die nächste davon.
        recognized = sorted(((self.sims[i], i) for _, i in candidates
                             if self.sims[i] is not None and self.sims[i] >= SIM_ACCEPT), reverse=True)
        if len(recognized) == 1 or (recognized and recognized[0][0] - recognized[1][0] >= SIM_MARGIN):
            best = recognized[0][1]
        elif recognized:
            ids = {i for _, i in recognized}
            best = next(i for _, i in candidates if i in ids)
        else:
            best = candidates[0][1]
        _, kpts, hx, hy = persons[best]
        return kpts, hx, hy

    def _by_identity(self, persons, max_dist):
        known = sorted(((sim, i) for i, sim in enumerate(self.sims) if sim is not None), reverse=True)
        unique = bool(known) and known[0][0] >= SIM_ACCEPT and (
            len(known) == 1 or known[0][0] - known[1][0] >= SIM_MARGIN)
        if not unique:
            self._confirm, self._confirm_pos = 0, None
            return None

        _, kpts, hx, hy = persons[known[0][1]]
        # Mehrere Bilder in Folge an (ungefähr) derselben Stelle → kein Zufallstreffer
        same_spot = (self._confirm_pos is not None
                     and np.hypot(hx - self._confirm_pos[0], hy - self._confirm_pos[1]) <= max_dist)
        self._confirm = self._confirm + 1 if same_spot else 1
        self._confirm_pos = (hx, hy)
        if self._confirm < CONFIRM_FRAMES:
            return None
        self._confirm, self._confirm_pos = 0, None
        return kpts, hx, hy

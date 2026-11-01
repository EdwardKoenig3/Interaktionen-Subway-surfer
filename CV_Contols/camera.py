import threading
from typing import Any, Optional, Tuple

import cv2


class LatestFrameReader:
    """Liest die Kamera in einem Hintergrund-Thread und behält nur das neueste Bild.

    Ohne das puffert OpenCV Bilder, sobald die Erkennung langsamer ist als die
    Kamera (z.B. auf der CPU) – die Steuerung hinkt dann immer weiter hinterher.
    So wird stets das aktuelle Bild ausgewertet, ältere werden verworfen.
    """

    def __init__(self, cap: cv2.VideoCapture):
        self.cap = cap
        self._cond = threading.Condition()
        self._frame: Optional[Any] = None
        self._seq = 0          # Nummer des neuesten Bildes
        self._read_seq = 0     # Nummer des zuletzt abgeholten Bildes
        self._alive = True     # False: Kamera liefert nichts mehr / beendet
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._alive:
            ok, frame = self.cap.read()
            with self._cond:
                if not ok:
                    self._alive = False
                else:
                    self._frame = frame
                    self._seq += 1
                self._cond.notify_all()

    def read(self, timeout: float = 2.0) -> Tuple[bool, Optional[Any]]:
        """Nächstes noch nicht ausgewertetes Bild – wartet ggf. bis `timeout` darauf."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq > self._read_seq or not self._alive, timeout)
            if self._seq == self._read_seq:
                return False, None
            self._read_seq = self._seq
            return True, self._frame

    def release(self) -> None:
        with self._cond:
            self._alive = False
        self._thread.join(timeout=1.0)
        self.cap.release()

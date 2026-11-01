"""
leaderboard.py – Persistente Top-10-Bestenliste, getrennt nach Steuerquelle.

Gespeichert wird in highscores.json neben dieser Datei:

    {
      "vision":   [{"name": "ANNA", "score": 4210, "coins": 12, "date": "2026-11-01"}, ...],
      "keyboard": [...],
      "voice":    [...]
    }

Nur Einzelspieler-Runden kommen in die Liste.

Darstellung: LeaderboardView zeigt eine Liste als Tabelle in camera.ui an.
"""

import json
import os
import shutil
from datetime import date
from pathlib import Path

from ursina import Text, camera, color, destroy

FILE = Path(__file__).resolve().parent / "highscores.json"
MAX_ENTRIES = 10
MAX_NAME_LEN = 12

SOURCE_LABEL = {'keyboard': 'TASTATUR', 'vision': 'VISION', 'voice': 'VOICE'}


# ── Speichern / Laden ─────────────────────────────────────────────────

def _load_all() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # Kaputte Datei sichern, statt sie beim nächsten Speichern zu überschreiben
        backup = FILE.with_suffix(".broken.json")
        try:
            shutil.copyfile(FILE, backup)
            print(f"[Bestenliste] {FILE.name} unlesbar ({e}) – gesichert als {backup.name}")
        except OSError:
            print(f"[Bestenliste] {FILE.name} unlesbar ({e})")
        return {}
    except OSError as e:
        print(f"[Bestenliste] {FILE.name} nicht lesbar ({e})")
        return {}
    return data if isinstance(data, dict) else {}


def _save_all(data: dict) -> None:
    # Erst in eine temporäre Datei schreiben, dann ersetzen → bei einem Absturz
    # während des Schreibens bleibt die alte Liste erhalten
    tmp = FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, FILE)
    except OSError as e:
        print(f"[Bestenliste] Speichern fehlgeschlagen: {e}")


def get_entries(source: str) -> list[dict]:
    """Top-10 einer Steuerquelle, absteigend nach Score."""
    entries = []
    for e in _load_all().get(source, []):
        if isinstance(e, dict) and isinstance(e.get("score"), int):
            entries.append({
                "name":  str(e.get("name", "???"))[:MAX_NAME_LEN],
                "score": e["score"],
                "coins": e.get("coins", 0),
                "date":  e.get("date", ""),
            })
    entries.sort(key=lambda e: e["score"], reverse=True)
    return entries[:MAX_ENTRIES]


def qualifies(source: str, score: int) -> bool:
    """True, wenn der Score in die Top 10 dieser Steuerquelle kommt."""
    if score <= 0:
        return False
    entries = get_entries(source)
    return len(entries) < MAX_ENTRIES or score > entries[-1]["score"]


def add_entry(source: str, name: str, score: int, coins: int) -> int | None:
    """Eintrag hinzufügen und speichern. Gibt den Platz (0-basiert) zurück,
    oder None, wenn der Score nicht (mehr) für die Top 10 reicht."""
    data = _load_all()
    entries = get_entries(source)
    new = {
        "name":  (name.strip() or "ANONYM")[:MAX_NAME_LEN],
        "score": int(score),
        "coins": int(coins),
        "date":  date.today().isoformat(),
    }
    # Bei gleichem Score bleibt der ältere Eintrag vorn
    index = next((i for i, e in enumerate(entries) if score > e["score"]), len(entries))
    if index >= MAX_ENTRIES:
        return None
    entries.insert(index, new)
    data[source] = entries[:MAX_ENTRIES]
    _save_all(data)
    return index


# ── Anzeige ───────────────────────────────────────────────────────────

class LeaderboardView:
    """Tabelle (Platz | Name | Score) in camera.ui.

    Eigene Text-Objekte pro Zeile und Spalte, damit die Spalten auch mit der
    Proportionalschrift sauber untereinander stehen und eine Zeile farbig
    hervorgehoben werden kann.
    """

    ROW_H = 0.036

    def __init__(self, x_center: float, y_top: float, width: float = 0.46, scale: float = 1.0):
        half = width / 2
        self._title = Text('', parent=camera.ui, origin=(0, 0), position=(x_center, y_top),
                           scale=1.2 * scale, color=color.yellow, z=-0.5)
        self._rows = []
        for i in range(MAX_ENTRIES):
            y = y_top - 0.05 - i * self.ROW_H
            rank  = Text('', parent=camera.ui, origin=(0.5, 0),  position=(x_center - half + 0.04, y),
                         scale=scale, z=-0.5)
            name  = Text('', parent=camera.ui, origin=(-0.5, 0), position=(x_center - half + 0.07, y),
                         scale=scale, z=-0.5)
            score = Text('', parent=camera.ui, origin=(0.5, 0),  position=(x_center + half, y),
                         scale=scale, z=-0.5)
            self._rows.append((rank, name, score))
        self.hide()

    def show(self, source: str, highlight: int | None = None) -> None:
        entries = get_entries(source)
        self._title.text = f'BESTENLISTE – {SOURCE_LABEL.get(source, source.upper())}'
        self._title.enabled = True
        for i, (rank, name, score) in enumerate(self._rows):
            col = color.yellow if i == highlight else color.white
            if i < len(entries):
                rank.text, name.text, score.text = f'{i + 1}.', entries[i]["name"], str(entries[i]["score"])
            elif i == 0:
                rank.text, name.text, score.text = '', 'noch keine Einträge', ''
                col = color.gray
            else:
                rank.text = name.text = score.text = ''
            for t in (rank, name, score):
                t.color = col
                t.enabled = True

    def hide(self) -> None:
        self._title.enabled = False
        for row in self._rows:
            for t in row:
                t.enabled = False

    def destroy(self) -> None:
        destroy(self._title)
        for row in self._rows:
            for t in row:
                destroy(t)
        self._rows = []

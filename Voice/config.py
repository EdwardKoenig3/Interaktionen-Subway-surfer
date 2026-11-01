import json
from pathlib import Path

_VOICE_DIR = Path(__file__).resolve().parent
_NETWORK_FILE = _VOICE_DIR.parent / "network.json"


def _load_network_config() -> tuple[str, int]:
    """Ziel-IP und Port aus network.json lesen. Fehlt die Datei: 127.0.0.1:9000."""
    ip, port = "127.0.0.1", 9000
    try:
        data = json.loads(_NETWORK_FILE.read_text(encoding="utf-8"))
        ip = data.get("target_ip", ip)
        port = int(data.get("port", port))
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, ValueError, OSError) as e:
        print(f"[Netzwerk] {_NETWORK_FILE.name} fehlerhaft ({e}) – nutze {ip}:{port}")
    return ip, port


MODEL_PATH = str(_VOICE_DIR / "model-us")
IP, PORT = _load_network_config()   # per --ip / --port in main.py überschreibbar
REF_FILE = str(_VOICE_DIR / "current_owner.wav")
FS = 16000
BLOCKSIZE = 600 # Für schnelle Reaktion

WORDS = ["left", "right", "hop", "cover","center"]
# WORDS = ["links", "rechts", "hoch", "ducken", "mitte"]
# "[unk]" fängt alles auf, was kein Befehlswort ist. Ohne es muss Vosk jedes
# Geräusch auf eines der Befehlswörter abbilden → Fehlauslöser.
GRAMMAR = json.dumps(WORDS + ["[unk]"], ensure_ascii=False)

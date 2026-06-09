import json
from pathlib import Path

MODEL_PATH = r"..\model-us"
IP = "192.168.16.50"
PORT = 9000
REF_FILE = "current_owner.wav"
FS = 16000
BLOCKSIZE = 600 # Für schnelle Reaktion

WORDS = ["left", "right", "jump", "duck", "middle"]
# WORDS = ["links", "rechts", "hoch", "ducken", "mitte"]
GRAMMAR = json.dumps(WORDS, ensure_ascii=False)
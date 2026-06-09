# from vosk import Model, KaldiRecognizer
# from config import MODEL_PATH, FS, GRAMMAR
# from pathlib import Path

# def init_vosk():
#     model_dir = Path(MODEL_PATH)
#     if not model_dir.exists():
#         raise FileNotFoundError(f"Modell nicht gefunden: {MODEL_PATH}")
    
#     model = Model(str(model_dir))
#     recognizer = KaldiRecognizer(model, FS, GRAMMAR)
#     return recognizer

from vosk import Model, KaldiRecognizer
from config import MODEL_PATH, FS, GRAMMAR
from pathlib import Path

def get_model():
    """Lädt das Modell einmalig, damit wir es für Kalibrierung und Main nutzen können."""
    model_dir = Path(MODEL_PATH)
    if not model_dir.exists():
        raise FileNotFoundError(f"Modell nicht gefunden: {MODEL_PATH}")
    return Model(str(model_dir))

def init_recognizer(model, grammar=GRAMMAR):
    """Erstellt einen Recognizer mit einer bestimmten Grammatik."""
    return KaldiRecognizer(model, FS, grammar)


import sounddevice as sd
from scipy.io import wavfile
import os
import json
import config
import numpy as np # Wichtig: NumPy importieren

def record_reference_smart(model):
    """Nimmt auf, bis das letzte Wort der Liste erkannt wurde."""
    print("\n" + "="*50)
    print("      SMARTE STIMMEN-KALIBRIERUNG")
    print("="*50)
    print("Bitte sprich folgenden Satz:")
    print(f"\n>>> {' '.join(config.WORDS)} <<<")
    print("\n(Die Aufnahme endet automatisch nach dem letzten Wort)")
    print("="*50)

    recorded_chunks = []
    last_word = config.WORDS[-1].lower()
    
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(model, config.FS, config.GRAMMAR)

    # Diese Variable steuert den Abbruch der Schleife
    finished = False

    def callback(indata, frames, time, status):
        nonlocal finished
        # indata ist ein CFFI-Buffer. Wir konvertieren ihn in ein NumPy-Array.
        # Da wir RawInputStream mit dtype='int16' nutzen:
        data_array = np.frombuffer(indata, dtype='int16').copy()
        recorded_chunks.append(data_array)
        
        # Vosk füttern
        if rec.AcceptWaveform(bytes(indata)):
            result = json.loads(rec.Result())
            if last_word in result.get("text", "").lower():
                finished = True

    # Stream starten
    with sd.RawInputStream(samplerate=config.FS, blocksize=1600, dtype='int16',
                           channels=1, callback=callback):
        
        while not finished:
            # Kleines Feedback in der Konsole
            partial = json.loads(rec.PartialResult()).get("partial", "")
            if partial:
                print(f"Höre zu: {partial}          ", end="\r")
            sd.sleep(100) # CPU entlasten

    print(f"\n\nLetztes Wort '{last_word}' erkannt!")

    # Alle Chunks zusammenfügen
    if recorded_chunks:
        full_recording = np.concatenate(recorded_chunks, axis=0)
        wavfile.write(config.REF_FILE, config.FS, full_recording)
        print(f"Referenz erfolgreich erstellt.")

def cleanup():
    if os.path.exists(config.REF_FILE):
        try:
            os.remove(config.REF_FILE)
            print(f"Sicherheits-Check: {config.REF_FILE} gelöscht.")
        except Exception as e:
            print(f"Fehler beim Löschen: {e}")
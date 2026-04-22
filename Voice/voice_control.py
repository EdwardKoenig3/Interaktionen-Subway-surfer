# import json
# import queue
# from pathlib import Path

# import sounddevice as sd
# from vosk import Model, KaldiRecognizer

# from taste_senden import sende_pfeiltaste
# from sende_command import map_command

# MODEL_PATH = "model-de"

# audio_queue = queue.Queue()

# WORDS = ["links", "rechts", "oben", "unten"]
# grammar = json.dumps(WORDS, ensure_ascii=False)


# def audio_callback(indata, frames, time_info, status):
#     if status:
#         print("Audio-Status:", status)
#     audio_queue.put(bytes(indata))


# def main():
#     model_dir = Path(MODEL_PATH)

#     if not model_dir.exists():
#         print(f"Fehler: Modellordner '{MODEL_PATH}' nicht gefunden.")
#         return

#     print("Lade Modell...")
#     model = Model(str(model_dir))
#     recognizer = KaldiRecognizer(model, 16000, grammar)

#     print("Sag: links / rechts / oben / unten")
#     print("Beenden mit STRG+C\n")

#     try:
#         with sd.RawInputStream(
#             samplerate=16000,
#             blocksize=8000,
#             dtype="int16",
#             channels=1,
#             callback=audio_callback
#         ):
#             while True:
#                 data = audio_queue.get()

#                 if recognizer.AcceptWaveform(data):
#                     result = json.loads(recognizer.Result())
#                     text = result.get("text", "").strip().lower()

#                     if text:
#                         print("Erkannt:", text)
#                         # sende_pfeiltaste(text)
#                         commands = map_command(text)
#                         print(f"Commands: \n", commands)

#                 else:
#                     partial = json.loads(recognizer.PartialResult()).get("partial", "")
#                     if partial:
#                         print("... hört:", partial, end="\r")

#     except KeyboardInterrupt:
#         print("\nProgramm beendet.")


# if __name__ == "__main__":
#     main()

import json
import queue
from pathlib import Path

import sounddevice as sd
from vosk import Model, KaldiRecognizer
from pythonosc.udp_client import SimpleUDPClient

from taste_senden import sende_pfeiltaste
from sende_command import map_command

MODEL_PATH = "model-de"
IP = "192.168.137.1"
PORT = 9000

audio_queue = queue.Queue()

WORDS = ["links", "rechts", "oben", "unten"]
grammar = json.dumps(WORDS, ensure_ascii=False)


def audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio-Status:", status)
    audio_queue.put(bytes(indata))


def main():
    model_dir = Path(MODEL_PATH)

    if not model_dir.exists():
        print(f"Fehler: Modellordner '{MODEL_PATH}' nicht gefunden.")
        return

    print("Lade Modell...")
    model = Model(str(model_dir))
    recognizer = KaldiRecognizer(model, 16000, grammar)
    client = SimpleUDPClient(IP, PORT)

    print("Sag: links / rechts / oben / unten")
    print("Beenden mit STRG+C\n")

    try:
        with sd.RawInputStream(
            samplerate=16000,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=audio_callback
        ):
            while True:
                data = audio_queue.get()

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip().lower()

                    if text:
                        print("Erkannt:", text)

                        commands = map_command(text)
                        print("Commands:", commands)

                        for address, value in commands:
                            client.send_message(address, value)
                            print(f"Sent: {address} {value}")

                else:
                    partial = json.loads(recognizer.PartialResult()).get("partial", "")
                    if partial:
                        print("... hört:", partial, end="\r")

    except KeyboardInterrupt:
        print("\nProgramm beendet.")


if __name__ == "__main__":
    main()
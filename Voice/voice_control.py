# import queue
# import json
# from pathlib import Path

# import sounddevice as sd
# from vosk import Model, KaldiRecognizer
# from pythonosc.udp_client import SimpleUDPClient

# from sende_command import map_command

# MODEL_PATH = "..\model-de"
# IP = "192.168.137.1"
# PORT = 9000

# audio_queue = queue.Queue()

# WORDS = ["links", "rechts", "oben", "unten", "mitte", "jump", "slide"]
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
#     client = SimpleUDPClient(IP, PORT)

#     print(f"Sende OSC an {IP}:{PORT}")
#     print("Sag: links / rechts / oben / unten")
#     print("Beenden mit STRG+C\n")

#     try:
#         with sd.RawInputStream(
#             samplerate=16000,
#             blocksize=4000,
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

#                         commands = map_command(text)
#                         print("Commands:", commands)

#                         for address, value in commands:
#                             client.send_message(address, value)
#                             print(f"Sent OSC: {address} {value}")

#                 else:
#                     partial = json.loads(recognizer.PartialResult()).get("partial", "")
#                     if partial:
#                         print("... hört:", partial, end="\r")

#     except KeyboardInterrupt:
#         print("\nProgramm beendet.")


# if __name__ == "__main__":
#     main()




# # import queue
# # import json
# # import time
# # from pathlib import Path

# # import sounddevice as sd
# # from vosk import Model, KaldiRecognizer
# # from pythonosc.udp_client import SimpleUDPClient

# # from sende_command import map_command
# # from speaker_check import is_correct_speaker


# # # -------- CONFIG --------
# # MODEL_PATH = "model-de"
# # REFERENCE_VOICE = "referenz.wav"

# # IP = "192.168.137.1"
# # PORT = 9000

# # SAMPLE_RATE = 16000
# # LISTEN_SECONDS = 2
# # COOLDOWN = 1.5

# # WORDS = ["links", "rechts", "oben", "unten"]
# # grammar = json.dumps(WORDS, ensure_ascii=False)

# # audio_queue = queue.Queue()


# # def log_state(state, msg=""):
# #     print(f"[{state}] {msg}")


# # def audio_callback(indata, frames, time_info, status):
# #     if status:
# #         print("Audio-Status:", status)

# #     audio_queue.put(bytes(indata))


# # def main():
# #     model_dir = Path(MODEL_PATH)

# #     if not model_dir.exists():
# #         print(f"Fehler: Vosk-Modellordner '{MODEL_PATH}' nicht gefunden.")
# #         return

# #     if not Path(REFERENCE_VOICE).exists():
# #         print(f"Fehler: '{REFERENCE_VOICE}' nicht gefunden.")
# #         print("Bitte zuerst record_reference.py ausführen.")
# #         return

# #     print("Lade Vosk-Modell...")
# #     model = Model(str(model_dir))
# #     recognizer = KaldiRecognizer(model, SAMPLE_RATE, grammar)

# #     client = SimpleUDPClient(IP, PORT)

# #     print("\n--- SYSTEM BEREIT ---")
# #     print(f"Sende OSC an {IP}:{PORT}")
# #     print("Befehle: links / rechts / oben / unten")
# #     print("Beenden mit STRG+C\n")

# #     buffer = b""
# #     last_trigger_time = 0

# #     bytes_per_second = SAMPLE_RATE * 2  # int16 = 2 Bytes
# #     needed_bytes = bytes_per_second * LISTEN_SECONDS

# #     try:
# #         with sd.RawInputStream(
# #             samplerate=SAMPLE_RATE,
# #             blocksize=8000,
# #             dtype="int16",
# #             channels=1,
# #             callback=audio_callback
# #         ):
# #             while True:
# #                 log_state("LISTENING", f"Sprich jetzt ({LISTEN_SECONDS} Sekunden)...")

# #                 buffer = b""

# #                 while len(buffer) < needed_bytes:
# #                     data = audio_queue.get()
# #                     buffer += data

# #                 current_time = time.time()

# #                 if current_time - last_trigger_time < COOLDOWN:
# #                     log_state("COOLDOWN", "Kurze Pause...")
# #                     continue

# #                 log_state("VERIFYING", "Prüfe Stimme...")
# #                 correct, score = is_correct_speaker(buffer)

# #                 if not correct:
# #                     log_state("REJECTED", f"Falsche Stimme oder zu unsicher. Score: {score:.2f}")
# #                     continue

# #                 log_state("ACCEPTED", f"Richtige Stimme erkannt. Score: {score:.2f}")

# #                 recognizer.AcceptWaveform(buffer)
# #                 result = json.loads(recognizer.Result())
# #                 text = result.get("text", "").strip().lower()

# #                 if not text:
# #                     log_state("NO_COMMAND", "Kein Befehl erkannt.")
# #                     continue

# #                 log_state("RECOGNIZED", text)

# #                 commands = map_command(text)

# #                 if not commands:
# #                     log_state("UNKNOWN", f"Kein Mapping für: {text}")
# #                     continue

# #                 for address, value in commands:
# #                     client.send_message(address, value)
# #                     log_state("SENT", f"{address} {value}")

# #                 last_trigger_time = time.time()

# #     except KeyboardInterrupt:
# #         print("\nProgramm beendet.")


# # if __name__ == "__main__":
# #     main()
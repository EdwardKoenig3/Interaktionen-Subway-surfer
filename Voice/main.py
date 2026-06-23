
import queue
import json
import time

import sounddevice as sd
from pythonosc.udp_client import SimpleUDPClient

import config
import audio_tools
import speech_engine

from sende_command import map_command
from low_latenz_filter import PartialCommandDetector


audio_queue = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    # Audio-Callback vom Mikrofon
    if status:
        print(f"Audio-Status: {status}")

    audio_queue.put(bytes(indata))


def main():

    print(f"Verbinde mit OSC: {config.IP}:{config.PORT}")

    client = SimpleUDPClient(config.IP, config.PORT)

    # Modell laden
    try:
        model = speech_engine.get_model()

    except Exception as e:
        print(f"Fehler beim Laden des Modells: {e}")
        return

    # Kalibrierung
    try:
        audio_tools.record_reference_smart(model)

    except Exception as e:
        print(f"Kalibrierung fehlgeschlagen: {e}")
        return

    # Recognizer starten
    recognizer = speech_engine.init_recognizer(model)

    # Sprachbefehle
    command_detector = PartialCommandDetector(

        command_keywords={

            "left": ["left"],
            "right": ["right"],
            "jump": ["jump", "hop", "up", "bounce" ],
            "duck": ["duck", "down","cover"],
            "middle": ["middle", "mid","center"]

        },

        confidence=0.9,
        required_hits=5,
        cooldown_ms=200,
        debug=False
    )

    print("\n" + "=" * 50)
    print(">>> ULTRA LOW LATENCY SYSTEM AKTIV <<<")
    print("=" * 50 + "\n")

    # Queue leeren
    with audio_queue.mutex:
        audio_queue.queue.clear()

    try:

        with sd.RawInputStream(
            samplerate=config.FS,
            blocksize=config.BLOCKSIZE,
            dtype="int16",
            channels=1,
            callback=audio_callback
        ):

            while True:

                data = audio_queue.get()

                # Finale Sprache
                if recognizer.AcceptWaveform(data):
                    recognizer.Result()

                else:

                    # Zeitpunkt direkt vor der Verarbeitung
                    processing_start = time.perf_counter()

                    # Partial Ergebnisse
                    partial_raw = recognizer.PartialResult()

                    partial_data = json.loads(partial_raw)

                    text = partial_data.get(
                        "partial",
                        ""
                    ).strip().lower()

                    if text:

                        print(f"[PARTIAL] {text}")

                        detected_command = (
                            command_detector.process_text(text)
                        )

                        if detected_command:

                            detection_time = time.perf_counter()

                            print(
                                f"[COMMAND] {detected_command}"
                            )

                            commands = map_command(
                                detected_command
                            )

                            if commands:

                                for address, value in commands:

                                    client.send_message(
                                        address,
                                        value
                                    )

                                send_time = time.perf_counter()

                                detection_ms = (
                                    detection_time - processing_start
                                ) * 1000

                                send_ms = (
                                    send_time - detection_time
                                ) * 1000

                                total_ms = (
                                    send_time - processing_start
                                ) * 1000

                                print(
                                    f"OSC GESENDET: {detected_command} | "
                                    f"Erkennung: {detection_ms:.2f} ms | "
                                    f"Senden: {send_ms:.2f} ms | "
                                    f"Gesamt: {total_ms:.2f} ms"
                                )

                                # Wichtig:
                                # verhindert Mehrfachtrigger
                                recognizer.Reset()

    except KeyboardInterrupt:

        print("\nSystem gestoppt.")

    finally:

        audio_tools.cleanup()


if __name__ == "__main__":
    main()
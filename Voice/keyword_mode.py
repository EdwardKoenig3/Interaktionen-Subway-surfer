import queue
import json
import time
import audioop

import sounddevice as sd
from pythonosc.udp_client import SimpleUDPClient

import config
import audio_tools
import speech_engine

from sende_command import map_command
from low_latenz_filter import PartialCommandDetector


audio_queue = queue.Queue(maxsize=3)


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"[AUDIO STATUS] {status}")

    data = bytes(indata)

    try:
        audio_queue.put_nowait(data)
    except queue.Full:
        try:
            audio_queue.get_nowait()
            print("[QUEUE] Voll - alter Audio-Block verworfen")
        except queue.Empty:
            pass

        try:
            audio_queue.put_nowait(data)
        except queue.Full:
            print("[QUEUE] Neuer Audio-Block konnte nicht eingefügt werden")


def main():
    print(f"[START] Verbinde mit OSC: {config.IP}:{config.PORT}")

    client = SimpleUDPClient(config.IP, config.PORT)

    try:
        print("[MODEL] Lade Sprachmodell...")
        model = speech_engine.get_model()
        print("[MODEL] Sprachmodell geladen")

    except Exception as e:
        print(f"[ERROR] Fehler beim Laden des Modells: {e}")
        return

    try:
        print("[CALIBRATION] Starte Kalibrierung...")
        audio_tools.record_reference_smart(model)
        print("[CALIBRATION] Kalibrierung abgeschlossen")

    except Exception as e:
        print(f"[ERROR] Kalibrierung fehlgeschlagen: {e}")
        return

    recognizer = speech_engine.init_recognizer(model)
    print("[RECOGNIZER] Recognizer gestartet")

    command_detector = PartialCommandDetector(
        command_keywords={
            "left": ["left"],
            "right": ["right"],
            "jump": ["jump", "hop"],
            "duck": ["duck", "down"],
            "middle": ["middle", "mid"]
        },
        confidence=0.8,
        required_hits=3,
        cooldown_ms=300,
        debug=True
    )

    print("[DETECTOR] PartialCommandDetector aktiv")
    print("\n" + "=" * 50)
    print(">>> ULTRA LOW LATENCY SYSTEM AKTIV <<<")
    print("=" * 50 + "\n")

    with audio_queue.mutex:
        audio_queue.queue.clear()
        print("[QUEUE] Audio-Queue geleert")

    last_partial_check = 0
    partial_interval = 0.04

    try:
        with sd.RawInputStream(
            samplerate=config.FS,
            blocksize=config.BLOCKSIZE,
            dtype="int16",
            channels=1,
            callback=audio_callback
        ):
            print("[AUDIO] Mikrofonstream gestartet")
            print(
                f"[AUDIO CONFIG] "
                f"FS={config.FS}, "
                f"BLOCKSIZE={config.BLOCKSIZE}"
            )

            while True:
                data = audio_queue.get()

                loop_start = time.perf_counter()

                volume = audioop.rms(data, 2)
                # print(f"[AUDIO] RMS={volume}")

                if recognizer.AcceptWaveform(data):
                    result_raw = recognizer.Result()

                    try:
                        result = json.loads(result_raw)
                        final_text = result.get("text", "").strip().lower()
                    except json.JSONDecodeError:
                        final_text = ""
                        print(f"[FINAL RAW ERROR] {result_raw}")

                    print(f"[FINAL] '{final_text}'")
                    continue

                now = time.monotonic()

                if now - last_partial_check < partial_interval:
                    continue

                last_partial_check = now

                partial_raw = recognizer.PartialResult()
                # print(f"[PARTIAL RAW] {partial_raw}")

                try:
                    partial_data = json.loads(partial_raw)
                except json.JSONDecodeError:
                    print("[ERROR] Partial JSON konnte nicht gelesen werden")
                    continue

                text = partial_data.get("partial", "").strip().lower()

                if not text:
                    # print("[PARTIAL TEXT] leer")
                    continue

                print(f"[PARTIAL TEXT] '{text}'")
                print(f"[DETECTOR INPUT] text='{text}'")

                detected_command = command_detector.process_text(text)

                print(f"[DETECTOR OUTPUT] {detected_command}")

                elapsed = (time.perf_counter() - loop_start) * 1000
                print(f"[LATENCY] {elapsed:.1f} ms")

                if not detected_command:
                    continue

                print(f"[COMMAND CANDIDATE] {detected_command}")

                commands = map_command(detected_command)

                if not commands:
                    print(f"[COMMAND REJECTED] Kein Mapping für {detected_command}")
                    continue

                for address, value in commands:
                    print(f"[OSC] address={address} value={value}")
                    client.send_message(address, value)

                print(f"[COMMAND ACCEPTED] {detected_command}")
                print(f"[OSC SENT] {detected_command}")

                recognizer.Reset()
                print("[RECOGNIZER] Reset nach Command")

    except KeyboardInterrupt:
        print("\n[STOP] System gestoppt.")

    finally:
        print("[CLEANUP] Räume Audio-Ressourcen auf...")
        audio_tools.cleanup()
        print("[CLEANUP] Fertig")


if __name__ == "__main__":
    main()
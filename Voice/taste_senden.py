from pynput.keyboard import Controller, Key
import time

keyboard = Controller()

RICHTUNGEN = {
    "links": Key.left,
    "rechts": Key.right,
    "oben": Key.up,
    "unten": Key.down,
}


def sende_pfeiltaste(wort):
    wort = wort.strip().lower()

    if wort not in RICHTUNGEN:
        print(f"Unbekannter Befehl: {wort}")
        return

    taste = RICHTUNGEN[wort]

    keyboard.press(taste)
    time.sleep(0.05)
    keyboard.release(taste)

    print(f"Taste gesendet: {wort}")
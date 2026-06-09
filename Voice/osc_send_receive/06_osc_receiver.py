#!/usr/bin/env python3
"""
06_osc_receiver.py

Very simple OSC receiver demo.

It shows that different OSC addresses are mapped
to different handler functions.
"""

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


IP = "127.0.0.1"
PORT = 9000


def on_hello(address, *args):
    print(f"on_hello()  address={address}  args={args}")


def on_number(address, *args):
    print(f"on_number() address={address}  args={args}")


def on_xy(address, *args):
    print(f"on_xy()     address={address}  args={args}")


def on_color(address, *args):
    print(f"on_color()  address={address}  args={args}")


def on_toggle(address, *args):
    print(f"on_toggle() address={address}  args={args}")


def main() -> None:
    dispatcher = Dispatcher()

    dispatcher.map("/demo/hello", on_hello)
    dispatcher.map("/demo/number", on_number)
    dispatcher.map("/demo/xy", on_xy)
    dispatcher.map("/demo/color", on_color)
    dispatcher.map("/demo/toggle", on_toggle)

    server = BlockingOSCUDPServer((IP, PORT), dispatcher)

    print(f"Listening for OSC on {IP}:{PORT}")
    print("Try sending:")
    print("  /demo/hello")
    print("  /demo/number")
    print("  /demo/xy")
    print("  /demo/color")
    print("  /demo/toggle")

    server.serve_forever()


if __name__ == "__main__":
    main()
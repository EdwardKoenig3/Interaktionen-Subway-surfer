#!/usr/bin/env python3
"""
06_osc_sender.py

Very simple OSC sender demo.

Goal:
- show how to send OSC messages
- show that different OSC addresses can call different methods
  on the receiver side

Keys:
    1   send /demo/hello "Hello from sender"
    2   send /demo/number 42
    3   send /demo/xy 0.25 0.75
    4   send /demo/color "red"
    5   send /demo/toggle 1
    6   send /demo/toggle 0
    q   quit
"""

from pythonosc.udp_client import SimpleUDPClient


IP = "192.168.137.1"
PORT = 9000


def send_hello(client: SimpleUDPClient) -> None:
    client.send_message("/demo/hello", "Hello from sender")
    print('Sent: /demo/hello "Hello from sender"')


def send_number(client: SimpleUDPClient) -> None:
    client.send_message("/demo/number", 42)
    print("Sent: /demo/number 42")


def send_xy(client: SimpleUDPClient) -> None:
    client.send_message("/demo/xy", [0.25, 0.75])
    print("Sent: /demo/xy 0.25 0.75")


def send_color(client: SimpleUDPClient) -> None:
    client.send_message("/demo/color", "red")
    print('Sent: /demo/color "red"')


def send_toggle_on(client: SimpleUDPClient) -> None:
    client.send_message("/demo/toggle", 1)
    print("Sent: /demo/toggle 1")


def send_toggle_off(client: SimpleUDPClient) -> None:
    client.send_message("/demo/toggle", 0)
    print("Sent: /demo/toggle 0")


def print_help() -> None:
    print(
        """
Simple OSC sender

Keys:
  1 -> /demo/hello   "Hello from sender"
  2 -> /demo/number  42
  3 -> /demo/xy      0.25 0.75
  4 -> /demo/color   "red"
  5 -> /demo/toggle  1
  6 -> /demo/toggle  0
  q -> quit
"""
    )


def main() -> None:
    client = SimpleUDPClient(IP, PORT)
    print(f"Sending OSC messages to {IP}:{PORT}")
    print_help()

    while True:
        key = input("Key: ").strip().lower()

        if key == "1":
            send_hello(client)
        elif key == "2":
            send_number(client)
        elif key == "3":
            send_xy(client)
        elif key == "4":
            send_color(client)
        elif key == "5":
            send_toggle_on(client)
        elif key == "6":
            send_toggle_off(client)
        elif key == "q":
            print("Bye.")
            break
        else:
            print("Unknown key.")
            print_help()


if __name__ == "__main__":
    main()
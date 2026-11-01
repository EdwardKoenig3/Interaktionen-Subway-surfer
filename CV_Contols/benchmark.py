"""
benchmark.py – Wie schnell läuft die Pose-Erkennung auf diesem Rechner?

Misst YOLO auf allen hier verfügbaren Wegen (PyTorch CPU/CUDA, OpenVINO auf
Intel-CPU/-GPU/-NPU) mit einem 1280x720-Testbild und dieselben Einstellungen
wie CvMain.py. Dazu die Wiedererkennung (identity.py) pro Person.

    uv run CV_Contols/benchmark.py
    uv run CV_Contols/benchmark.py --imgsz 480 --threads 4
"""

import argparse
import statistics
import time
from pathlib import Path

import cv2
import torch
import ultralytics

import identity
import tracker
from CvMain import _load_model, _openvino_available, _openvino_device


def _measure(fn, n: int) -> float:
    for _ in range(3):
        fn()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


def main() -> None:
    parser = argparse.ArgumentParser(description="YOLO-Pose-Geschwindigkeit auf diesem Rechner messen")
    parser.add_argument("--imgsz", type=int, default=640, help="Inferenzauflösung (Default 640)")
    parser.add_argument("--threads", type=int, default=None, help="CPU-Threads für PyTorch (Default: alle Kerne)")
    parser.add_argument("-n", type=int, default=50, help="Durchläufe pro Gerät (Default 50)")
    args = parser.parse_args()

    if args.threads:
        torch.set_num_threads(args.threads)
    frame = cv2.resize(cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "zidane.jpg")), (1280, 720))
    h, w = frame.shape[:2]

    devices = ["cpu"]
    if torch.cuda.is_available():
        devices.append("cuda:0")
    if _openvino_available():
        import openvino as ov
        print(f"OpenVINO-Geräte: {ov.Core().available_devices}")
        for wanted in ("intel:cpu", "intel:gpu", "intel:npu"):
            mapped = _openvino_device(wanted)
            if mapped not in devices:
                devices.append(mapped)
    else:
        print("OpenVINO nicht installiert – nur PyTorch wird gemessen.")

    results = {}
    for device in devices:
        print(f"\n── {device} ──")
        model, used, imgsz = _load_model(device, args.imgsz, w, h)
        if used != device:
            print(f"{device} nicht nutzbar – übersprungen.")
            continue
        ms = _measure(lambda: model.predict(frame, conf=0.5, verbose=False, device=used, imgsz=imgsz), args.n)
        results[device] = ms
        print(f"{device}: {ms:.1f} ms pro Bild (~{1000 / ms:.0f} FPS), imgsz {imgsz}")

    # Wiedererkennung: Farbprofil pro Person (läuft immer auf der CPU)
    persons = tracker.extract_persons(model.predict(frame, conf=0.5, verbose=False, device=used, imgsz=imgsz))
    if persons:
        kpts = persons[0][1]
        ms = _measure(lambda: identity.appearance(frame, kpts), args.n)
        print(f"\nWiedererkennung (Farbprofil): {ms:.2f} ms pro Person")

    if results:
        best = min(results, key=results.get)
        fps = 1000 / results[best]
        verdict = ("gut spielbar" if fps >= 25 else "spielbar" if fps >= 15
                   else "zu langsam – kleinere --imgsz (z.B. 480) probieren")
        print(f"\nAm schnellsten: {best} mit ~{fps:.0f} FPS → {verdict}.")
        print("Hinweis: Läuft das Spiel auf demselben PC, bleibt etwas weniger übrig.")


if __name__ == "__main__":
    main()

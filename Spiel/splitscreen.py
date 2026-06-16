"""
splitscreen.py – Render-Setup für Zwei-Spieler-Splitscreen.

Es gibt nur EINE geteilte Spielwelt (gleiche Hindernisse/Kacheln). Zwei Kameras
rendern sie nebeneinander:
    • cam1 = Ursinas Hauptkamera  → linke Bildschirmhälfte
    • cam2 = zusätzliche Panda3D-Kamera an einer Ursina-Rig-Entity → rechte Hälfte

Damit jede Seite nur ihre EIGENE Spielfigur + Münzen zeigt, werden diese per
Panda3D-Kamera-Maske vor der jeweils anderen Kamera versteckt. Geteilte Entities
(Hindernisse, Boden, Gebäude, Himmel) behalten ihre Default-Maske und erscheinen
in beiden Hälften.

Kein Webcam-/Videobild – nur zwei 3D-Renderansichten derselben Klötzchen-Welt.
"""

from panda3d.core import Camera as PandaCamera, PerspectiveLens, BitMask32
from ursina import Entity, scene, application, window, camera, lerp, destroy, color
import random

# Kamera-Masken-Bits (innerhalb der Default-Maske 0x7FFFFFFF)
cam1_mask = BitMask32.bit(1)   # linke Kamera / Spieler 1
cam2_mask = BitMask32.bit(2)   # rechte Kamera / Spieler 2

# Kamera-Folge-Parameter (entsprechen der Single-Player-Kamera)
CAM_Y      = 6.0
CAM_ROT_X  = 18.0
CAM_Z_BASE = -18.0

_state = {
    'active':        False,
    'cam2_rig':      None,
    'cam2_np':       None,
    'dr_left':       None,
    'dr_right':      None,
    'divider':       None,
    'orig_cam_mask': None,   # ursprüngliche Kamera-Maske der Hauptkamera
}


def _half_aspect() -> float:
    win = application.base.win
    return (win.get_x_size() * 0.5) / max(win.get_y_size(), 1)


def setup_splitscreen():
    """Hauptkamera auf linke Hälfte stauchen und rechte Kamera erzeugen."""
    base = application.base
    win  = base.win

    # ── linke Hälfte: Hauptkamera ────────────────────────────────────
    if _state['orig_cam_mask'] is None:
        _state['orig_cam_mask'] = base.camNode.get_camera_mask()
    dr_left = base.camNode.get_display_region(0)
    dr_left.set_dimensions(0, 0.5, 0, 1)
    dr_left.set_clear_color_active(True)
    dr_left.set_clear_color(window.color)
    dr_left.set_clear_depth_active(True)
    base.camNode.set_camera_mask(cam1_mask)
    base.camLens.set_aspect_ratio(_half_aspect())

    # ── rechte Hälfte: zweite Kamera an Rig-Entity ───────────────────
    cam2_rig  = Entity(name='cam2_rig', eternal=True)   # parent = scene
    cam2_node = PandaCamera('cam2')
    lens = PerspectiveLens()
    lens.set_fov(camera.fov)
    lens.set_aspect_ratio(_half_aspect())
    cam2_node.set_lens(lens)
    cam2_node.set_camera_mask(cam2_mask)
    cam2_np = cam2_rig.attach_new_node(cam2_node)       # Identity-Transform

    dr_right = win.make_display_region(0.5, 1, 0, 1)
    dr_right.set_sort(0)
    dr_right.set_camera(cam2_np)
    dr_right.set_clear_color_active(True)
    dr_right.set_clear_color(window.color)
    dr_right.set_clear_depth_active(True)

    # Startposition wie Hauptkamera
    cam2_rig.position   = (0, CAM_Y, CAM_Z_BASE)
    cam2_rig.rotation_x = CAM_ROT_X

    # dünne Trennlinie in der Bildmitte (UI, fensterweit)
    divider = Entity(parent=camera.ui, model='quad', color=color.black,
                     scale=(0.006, 2), position=(0, 0), z=-1, eternal=True)

    _state.update(active=True, cam2_rig=cam2_rig, cam2_np=cam2_np,
                  dr_left=dr_left, dr_right=dr_right, divider=divider)
    return cam2_rig


def teardown_splitscreen():
    """Zurück auf Vollbild (für 1P-Modus / Menü)."""
    base = application.base
    win  = base.win
    if _state['dr_right'] is not None:
        win.remove_display_region(_state['dr_right'])
    dr_left = base.camNode.get_display_region(0)
    dr_left.set_dimensions(0, 1, 0, 1)
    if _state['orig_cam_mask'] is not None:
        base.camNode.set_camera_mask(_state['orig_cam_mask'])
    base.camLens.set_aspect_ratio(window.aspect_ratio)
    if _state['cam2_rig'] is not None:
        destroy(_state['cam2_rig'])
    if _state['divider'] is not None:
        destroy(_state['divider'])
    _state.update(active=False, cam2_rig=None, cam2_np=None,
                  dr_left=None, dr_right=None, divider=None)


def cam2_rig():
    return _state['cam2_rig']


def is_active() -> bool:
    return _state['active']


def follow_camera(cam_ent, player, state, dt):
    """Positioniert eine Kamera-Entity sanft hinter ihrem Spieler (mit Shake)."""
    cam_x = player.x * 0.25
    if state.shake_t > 0:
        cam_x += random.uniform(-0.45, 0.45) * (state.shake_t / 0.5)
    cam_ent.x = lerp(cam_ent.x, cam_x, min(7 * dt, 1))
    cam_ent.z = lerp(cam_ent.z, CAM_Z_BASE + player.z * 0.35, min(10 * dt, 1))
    cam_ent.y = CAM_Y
    cam_ent.rotation_x = CAM_ROT_X

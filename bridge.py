#!/usr/bin/env python3
"""
Keychron Rotary Knob & NumPad to Virtual MIDI Bridge for Ableton Live
Translates Keychron F13-F19 and NumPad 1-9 keystrokes into clean MIDI CC messages.
Dynamically tracks Command (CMD), Control (CTRL), and Shift modifiers.
Shift + Click (F15) toggles Device On/Off (Bypass) for instant A/B testing.
"""

import sys
import time
import subprocess
import argparse
import mido
import ctypes
from pynput import keyboard


# Load CoreGraphics for native synthesized scroll events
coregraphics = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')

coregraphics.CGEventCreateScrollWheelEvent2.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
coregraphics.CGEventCreateScrollWheelEvent2.restype = ctypes.c_void_p
coregraphics.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
coregraphics.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
coregraphics.CFRelease.argtypes = [ctypes.c_void_p]

kCGScrollEventUnitLine = 1
kCGHIDEventTap = 0
kCGEventFlagMaskAlternate = 0x00080000
kCGEventFlagMaskShift     = 0x00020000

# Virtual MIDI Device Name (Appears directly in Ableton Live)
MIDI_PORT_NAME = "Keychron K17 Max MIDI"
MIDI_CHANNEL = 15         # MIDI Channel 16 (0-indexed 15) to guarantee ZERO collision with Arturia (Ch 2 & 10)

# CC Assignments (Outside Arturia's CC range)
CC_TRACK_NAV = 86         # Normal Knob -> Track Navigation (CC 86)
CC_DEVICE_NAV = 88        # CTRL + Knob -> Device / Plugin Navigation (CC 88)
CC_VOLUME = 80            # CMD + Knob -> Selected Track Volume (CC 80)
CC_PAN = 85               # CMD + Shift + Knob -> Selected Track Pan (CC 85)
CC_TIMELINE_SCRUB = 89    # Shift + Knob -> Timeline Scrub (CC 89)

CC_PLUGIN_TOGGLE = 81     # Normal Click (F15) -> Toggle Plugin Window (CC 81)
CC_DEVICE_ON_OFF = 87     # Shift + Click (F15) -> Toggle Device On/Off / Bypass A-B (CC 87)

CC_F17 = 82               # F17 Button (Free)
CC_F18 = 83               # F18 Button (Free)
CC_F19 = 84               # F19 Button (Free)

# NumPad 1-9 to MIDI CC Map (CC 91 -> Marker 1, CC 92 -> Marker 2, ... CC 99 -> Marker 9)
NUMPAD_VK_MAP = {
    83: (91, 1),
    84: (92, 2),
    85: (93, 3),
    86: (94, 4),
    87: (95, 5),
    88: (96, 6),
    89: (97, 7),
    91: (98, 8),
    92: (99, 9)
}

# Modifier Key Sets (handling all macOS left/right variants)
SHIFT_KEYS = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}
CTRL_KEYS  = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
CMD_KEYS   = {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r}
OPT_KEYS   = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r}


class KeychronMidiBridge:
    def __init__(self, step_size=1, channel=MIDI_CHANNEL):
        self.step_size = step_size
        self.channel = channel
        self.shift_pressed = False
        self.ctrl_pressed = False
        self.cmd_pressed = False
        self.opt_pressed = False
        self.kb_controller = keyboard.Controller()

        # Open virtual MIDI port
        try:
            self.outport = mido.open_output(MIDI_PORT_NAME, virtual=True)
            print(f"[MIDI] Virtual port created: '{MIDI_PORT_NAME}'")
        except Exception as e:
            print(f"[WARN] Could not create virtual port, falling back to default: {e}")
            self.outport = mido.open_output()

        print(f"[MIDI] Channel: {self.channel + 1} (isolated from Arturia)")
        print("[READY] Control layers active:")
        print("   - Knob alone          -> Track Navigation (native scroll)")
        print("   - CTRL + Knob         -> Device/Plugin Navigation (CC 88)")
        print("   - CMD + Knob          -> Track Volume (CC 80, 0.5 dB steps)")
        print("   - CMD + Shift + Knob  -> Track Pan (CC 85, 5 pt steps)")
        print("   - Click (F15)         -> Toggle Plugin Window (CC 81)")
        print("   - Shift + Click (F15) -> Toggle Device On/Off A/B (CC 87)")
        print("   - NumPad 1-9          -> Marker/Locator Jump 1-9 (CC 91-99)")
        print("   - F17, F18, F19       -> CC 82, 83, 84 (free)")
        print("=" * 70)

    def on_press(self, key):
        try:
            # Track modifier keys (Left & Right)
            if key in SHIFT_KEYS:
                self.shift_pressed = True
            elif key in CTRL_KEYS:
                self.ctrl_pressed = True
            elif key in CMD_KEYS:
                self.cmd_pressed = True
            elif key in OPT_KEYS:
                self.opt_pressed = True

            # Rotary Knob: Rotate Left (CCW)
            elif key == keyboard.Key.f13:
                self._handle_knob_rotate(clockwise=False)

            # Rotary Knob: Rotate Right (CW)
            elif key == keyboard.Key.f14:
                self._handle_knob_rotate(clockwise=True)

            # Rotary Knob: Click Press
            elif key == keyboard.Key.f15:
                if self.shift_pressed:
                    self._send_button_press(CC_DEVICE_ON_OFF, "Shift + Click (Plugin On/Off A-B)")
                elif self.ctrl_pressed and self.cmd_pressed:
                    print("[ACTION] Ctrl + Cmd + Click -> Open Plugin Menu")
                    subprocess.run(["open", "hammerspoon://pluginmenu"])
                else:
                    self._send_button_press(CC_PLUGIN_TOGGLE, "Click (Toggle Plugin Window)")

            # NumPad 1-9 (Cubase-style Marker Jump)
            elif hasattr(key, 'vk') and key.vk in NUMPAD_VK_MAP:
                cc_num, marker_idx = NUMPAD_VK_MAP[key.vk]
                self._send_button_press(cc_num, f"NumPad {marker_idx} -> Marker {marker_idx}")

            # Extra Function Keys
            elif key == keyboard.Key.f17:
                self._send_button_press(CC_F17, "F17 Key")
            elif key == keyboard.Key.f18:
                self._send_button_press(CC_F18, "F18 Key")
            elif key == keyboard.Key.f19:
                self._send_button_press(CC_F19, "F19 Key")
        except Exception as e:
            print(f"[ERROR] handling key press: {e}")

    def on_release(self, key):
        try:
            # Track modifiers release (Left & Right)
            if key in SHIFT_KEYS:
                self.shift_pressed = False
            elif key in CTRL_KEYS:
                self.ctrl_pressed = False
            elif key in CMD_KEYS:
                self.cmd_pressed = False
            elif key in OPT_KEYS:
                self.opt_pressed = False

            # Rotary Knob Click Release
            elif key == keyboard.Key.f15:
                self._send_button_release(CC_DEVICE_ON_OFF, "Shift + Click")
                self._send_button_release(CC_PLUGIN_TOGGLE, "Click")

            # NumPad Release
            elif hasattr(key, 'vk') and key.vk in NUMPAD_VK_MAP:
                cc_num, _ = NUMPAD_VK_MAP[key.vk]
                self._send_button_release(cc_num, "NumPad")

            # Extra Function Keys Release
            elif key == keyboard.Key.f17:
                self._send_button_release(CC_F17, "F17 Key")
            elif key == keyboard.Key.f18:
                self._send_button_release(CC_F18, "F18 Key")
            elif key == keyboard.Key.f19:
                self._send_button_release(CC_F19, "F19 Key")
        except Exception as e:
            pass

    def _handle_knob_rotate(self, clockwise=True):
        val = min(127, 64 + self.step_size) if clockwise else max(0, 64 - self.step_size)
        direction = "CW" if clockwise else "CCW"

        # 1. CMD + Shift -> Pan
        if self.cmd_pressed and self.shift_pressed:
            msg = mido.Message('control_change', channel=self.channel, control=CC_PAN, value=val)
            self.outport.send(msg)
            print(f"{direction} | CMD + Shift + Knob (Pan) -> CC {CC_PAN} (Val {val})")

        # 2. Shift alone -> Timeline Scrub
        elif self.shift_pressed and not self.cmd_pressed and not self.ctrl_pressed and not self.opt_pressed:
            msg = mido.Message('control_change', channel=self.channel, control=CC_TIMELINE_SCRUB, value=val)
            self.outport.send(msg)
            print(f"{direction} | Shift + Knob (Timeline Scrub) -> CC {CC_TIMELINE_SCRUB} (Val {val})")

        # 2. CMD alone -> Volume
        elif self.cmd_pressed:
            msg = mido.Message('control_change', channel=self.channel, control=CC_VOLUME, value=val)
            self.outport.send(msg)
            print(f"{direction} | CMD + Knob (Volume) -> CC {CC_VOLUME} (Val {val})")

        # 3. CTRL alone -> Device / Plugin Navigation
        elif self.ctrl_pressed:
            msg = mido.Message('control_change', channel=self.channel, control=CC_DEVICE_NAV, value=val)
            self.outport.send(msg)
            print(f"{direction} | CTRL + Knob (Device Nav) -> CC {CC_DEVICE_NAV} (Val {val})")

        # 5. Normal Knob -> Option+Shift scroll for Arrangement track scroll + MIDI selection
        else:
            self._emit_option_shift_scroll(clockwise)
            msg = mido.Message('control_change', channel=self.channel, control=CC_TRACK_NAV, value=val)
            self.outport.send(msg)
            print(f"{direction} | Knob (Track Scroll Auto) -> Sent Opt+Shift Scroll + CC {CC_TRACK_NAV}")

    def _emit_option_shift_scroll(self, clockwise):
        try:
            delta = -2 if clockwise else 2
            event = coregraphics.CGEventCreateScrollWheelEvent2(None, kCGScrollEventUnitLine, 2, delta, 0, 0)
            if event:
                flags = kCGEventFlagMaskAlternate | kCGEventFlagMaskShift
                coregraphics.CGEventSetFlags(event, flags)
                coregraphics.CGEventPost(kCGHIDEventTap, event)
                coregraphics.CFRelease(event)
        except Exception as e:
            print(f"[ERROR] synthesizing scroll event: {e}")

    def _send_button_press(self, cc, name):
        print(f"[BTN] {name} Pressed -> CC {cc} (127)")
        msg = mido.Message('control_change', channel=self.channel, control=cc, value=127)
        self.outport.send(msg)

    def _send_button_release(self, cc, name):
        msg = mido.Message('control_change', channel=self.channel, control=cc, value=0)
        self.outport.send(msg)

    def run(self):
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Keychron Rotary Knob & NumPad to Virtual MIDI Bridge")
    parser.add_argument('--step', type=int, default=1, help="Step multiplier (default: 1)")
    parser.add_argument('--channel', type=int, default=16, help="MIDI Channel 1-16 (default: 16)")
    args = parser.parse_args()

    bridge = KeychronMidiBridge(step_size=args.step, channel=args.channel - 1)
    bridge.run()

#!/usr/bin/env python3
"""
Keychron Rotary Knob & NumPad to Virtual MIDI Bridge for Ableton Live
Translates Keychron F13-F19 and NumPad 1-9 keystrokes into clean MIDI CC messages.
Dynamically tracks Command (CMD), Control (CTRL), and Shift modifiers.
Uses selective macOS Quartz CGEventTap to suppress raw F17/F18/F19 key events when Ableton Live is frontmost.
"""

import sys
import time
import subprocess
import argparse
import ctypes
import queue
import threading
import mido
from pynput import keyboard


# Load CoreGraphics & CoreFoundation
coregraphics = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
corefoundation = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
objc = ctypes.CDLL('/usr/lib/libobjc.dylib')

# CoreGraphics function signatures
coregraphics.CGEventGetFlags.argtypes = [ctypes.c_void_p]
coregraphics.CGEventGetFlags.restype = ctypes.c_uint64
coregraphics.CGEventSourceFlagsState.argtypes = [ctypes.c_uint32]
coregraphics.CGEventSourceFlagsState.restype = ctypes.c_uint64

coregraphics.CGEventTapCreate.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
coregraphics.CGEventTapCreate.restype = ctypes.c_void_p
coregraphics.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]
coregraphics.CGEventTapEnable.restype = None
coregraphics.CGEventGetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
coregraphics.CGEventGetIntegerValueField.restype = ctypes.c_int64

# CoreFoundation function signatures
corefoundation.CFMachPortCreateRunLoopSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
corefoundation.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p
corefoundation.CFRunLoopGetCurrent.argtypes = []
corefoundation.CFRunLoopGetCurrent.restype = ctypes.c_void_p
corefoundation.CFRunLoopAddSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
corefoundation.CFRunLoopAddSource.restype = None
corefoundation.CFRunLoopRemoveSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
corefoundation.CFRunLoopRemoveSource.restype = None
corefoundation.CFRunLoopRunInMode.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_bool]
corefoundation.CFRunLoopRunInMode.restype = ctypes.c_int32
corefoundation.CFRelease.argtypes = [ctypes.c_void_p]

kCFRunLoopCommonModes = ctypes.c_void_p.in_dll(corefoundation, 'kCFRunLoopCommonModes')
kCFRunLoopDefaultMode = ctypes.c_void_p.in_dll(corefoundation, 'kCFRunLoopDefaultMode')

# CoreGraphics Constants
kCGHIDEventTap = 0
kCGSessionEventTap = 1
kCGHeadInsertEventTap = 0
kCGEventTapOptionDefault = 0

kCGEventKeyDown = 10
kCGEventKeyUp = 11
kCGEventTapDisabledByTimeout = 0xFFFFFFFF
kCGEventTapDisabledByUserInput = 0xFFFFFFFE
kCGKeyboardEventKeycode = 9

# Virtual Key Codes for Knob / Wheel
VK_F17 = 64  # Rotate CCW
VK_F18 = 79  # Click
VK_F19 = 80  # Rotate CW

# CoreGraphics modifier flag bitmasks
kCGEventFlagMaskCommand   = 0x00100000
kCGEventFlagMaskShift     = 0x00020000
kCGEventFlagMaskControl   = 0x00040000
kCGEventFlagMaskAlternate = 0x00080000

# Objective-C messaging setup for frontmost app check
objc.objc_getClass.argtypes = [ctypes.c_char_p]
objc.objc_getClass.restype = ctypes.c_void_p
objc.sel_registerName.argtypes = [ctypes.c_char_p]
objc.sel_registerName.restype = ctypes.c_void_p

_msgSend_void = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))
_msgSend_char_p = ctypes.CFUNCTYPE(ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))

_NSWorkspace_class = objc.objc_getClass(b'NSWorkspace')
_sel_sharedWorkspace = objc.sel_registerName(b'sharedWorkspace')
_sel_frontmostApplication = objc.sel_registerName(b'frontmostApplication')
_sel_localizedName = objc.sel_registerName(b'localizedName')
_sel_bundleIdentifier = objc.sel_registerName(b'bundleIdentifier')
_sel_UTF8String = objc.sel_registerName(b'UTF8String')

def is_ableton_frontmost():
    try:
        ws = _msgSend_void(_NSWorkspace_class, _sel_sharedWorkspace)
        if not ws:
            return False
        app = _msgSend_void(ws, _sel_frontmostApplication)
        if not app:
            return False

        loc_name_ptr = _msgSend_void(app, _sel_localizedName)
        bundle_id_ptr = _msgSend_void(app, _sel_bundleIdentifier)

        loc_name = ""
        if loc_name_ptr:
            s = _msgSend_char_p(loc_name_ptr, _sel_UTF8String)
            if s:
                loc_name = s.decode('utf-8', errors='ignore').lower()

        bundle_id = ""
        if bundle_id_ptr:
            s = _msgSend_char_p(bundle_id_ptr, _sel_UTF8String)
            if s:
                bundle_id = s.decode('utf-8', errors='ignore').lower()

        return ("ableton" in loc_name or "live" in loc_name or "com.ableton" in bundle_id)
    except Exception:
        return False


# CGEventTap callback prototype
CGEventTapCallBack = ctypes.CFUNCTYPE(
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.c_void_p
)

# MIDI Settings
MIDI_PORT_NAME = "Keychron K17 Max MIDI"
MIDI_CHANNEL = 15

# CC Assignments
CC_DEVICE_NAV = 88
CC_VOLUME = 80
CC_PAN = 85
CC_TIMELINE_SCRUB = 89
CC_CLIP_GAIN = 90

CC_PLUGIN_TOGGLE = 81
CC_DEVICE_ON_OFF = 87

CC_BTN_F14 = 101
CC_BTN_F15 = 102
CC_MONITORING_MODE = 103
CC_CUE_VOLUME = 104

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

        self.tap_port = None
        self.tap_source = None
        self.run_loop = None
        self._tap_callback_ref = None
        self.listener = None

        self.event_queue = queue.Queue()
        self.worker_thread = None
        self.running = False

        try:
            self.outport = mido.open_output(MIDI_PORT_NAME, virtual=True)
            print(f"[MIDI] Virtual port created: '{MIDI_PORT_NAME}'")
        except Exception as e:
            print(f"[WARN] Could not create virtual port, falling back to default: {e}")
            self.outport = mido.open_output()

        print(f"[MIDI] Channel: {self.channel + 1} (isolated from Arturia)")
        print("[READY] Control layers active:")
        print("   - Knob alone          -> AI Knob (Hammerspoon)")
        print("   - Option + Shift + Knob -> Fine AI Knob (Hammerspoon)")
        print("   - CTRL + Knob         -> Device/Plugin Navigation (CC 88)")
        print("   - CMD + Knob          -> Track Volume (CC 80, 0.5 dB steps)")
        print("   - CMD + Shift + Knob  -> Track Pan (CC 85, 5 pt steps)")
        print("   - Ctrl + Shift + Knob -> Cue Volume (CC 104)")
        print("   - Click (F18)         -> Toggle Plugin Window (CC 81)")
        print("   - Shift + Click (F18) -> Toggle Device On/Off A/B (CC 87)")
        print("   - Ctrl+Cmd+Click(F18) -> Cycle Track Monitoring Mode (CC 103)")
        print("   - NumPad 1-9          -> Marker/Locator Jump 1-9 (CC 91-99)")
        print("   - F13                 -> Open Plugin Menu")
        print("   - F14, F15            -> CC 101, 102 (free physical buttons)")
        print("=" * 70)

    def _get_live_modifiers(self, event=None):
        if event:
            flags = coregraphics.CGEventGetFlags(event)
        else:
            flags = coregraphics.CGEventSourceFlagsState(0) | coregraphics.CGEventSourceFlagsState(1)
        cmd = bool(flags & kCGEventFlagMaskCommand) or self.cmd_pressed
        shift = bool(flags & kCGEventFlagMaskShift) or self.shift_pressed
        ctrl = bool(flags & kCGEventFlagMaskControl) or self.ctrl_pressed
        opt = bool(flags & kCGEventFlagMaskAlternate) or self.opt_pressed
        return cmd, shift, ctrl, opt

    def _event_worker(self):
        while self.running:
            try:
                item = self.event_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                task_type = item[0]
                if task_type == 'rotate':
                    _, clockwise, modifiers = item
                    self._handle_knob_rotate(clockwise=clockwise, modifiers=modifiers)
                elif task_type == 'click_down':
                    _, modifiers = item
                    cmd, shift, ctrl, opt = modifiers
                    if shift:
                        self._send_button_press(CC_DEVICE_ON_OFF, "Shift + Click (Plugin On/Off A-B)")
                    elif ctrl and cmd:
                        self._send_button_press(CC_MONITORING_MODE, "Ctrl + Cmd + Click (Monitoring Mode)")
                    else:
                        self._send_button_press(CC_PLUGIN_TOGGLE, "Click (Toggle Plugin Window)")
                elif task_type == 'click_up':
                    self._send_button_release(CC_DEVICE_ON_OFF, "Shift + Click")
                    self._send_button_release(CC_PLUGIN_TOGGLE, "Click")
                    self._send_button_release(CC_MONITORING_MODE, "Ctrl + Cmd + Click")
            except Exception as e:
                print(f"[ERROR] processing queued event: {e}")
            finally:
                self.event_queue.task_done()

    def _quartz_tap_callback(self, proxy, event_type, event, refcon):
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            if self.tap_port:
                coregraphics.CGEventTapEnable(self.tap_port, True)
            return event

        if event_type in (kCGEventKeyDown, kCGEventKeyUp):
            keycode = coregraphics.CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            if keycode in (VK_F17, VK_F18, VK_F19):
                if is_ableton_frontmost():
                    modifiers = self._get_live_modifiers(event)
                    if event_type == kCGEventKeyDown:
                        if keycode == VK_F17:
                            self.event_queue.put(('rotate', False, modifiers))
                        elif keycode == VK_F19:
                            self.event_queue.put(('rotate', True, modifiers))
                        elif keycode == VK_F18:
                            self.event_queue.put(('click_down', modifiers))
                    elif event_type == kCGEventKeyUp:
                        if keycode == VK_F18:
                            self.event_queue.put(('click_up', modifiers))

                    # Return None to consume F17/F18/F19 key events so Ableton/macOS receives no raw key press
                    return None

        return event

    def _init_quartz_tap(self):
        self._tap_callback_ref = CGEventTapCallBack(self._quartz_tap_callback)
        mask = (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp)

        self.tap_port = coregraphics.CGEventTapCreate(
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            mask,
            self._tap_callback_ref,
            None
        )

        if not self.tap_port:
            # Fallback to session tap
            self.tap_port = coregraphics.CGEventTapCreate(
                kCGSessionEventTap,
                kCGHeadInsertEventTap,
                kCGEventTapOptionDefault,
                mask,
                self._tap_callback_ref,
                None
            )

        if not self.tap_port:
            print("[FATAL ERROR] Unable to create macOS Quartz CGEventTap for F17/F18/F19 key suppression.")
            print("              Please ensure Terminal / Python has Accessibility permissions in macOS System Settings.")
            sys.exit(1)

        self.tap_source = corefoundation.CFMachPortCreateRunLoopSource(None, self.tap_port, 0)
        self.run_loop = corefoundation.CFRunLoopGetCurrent()
        corefoundation.CFRunLoopAddSource(self.run_loop, self.tap_source, kCFRunLoopCommonModes)
        coregraphics.CGEventTapEnable(self.tap_port, True)
        print("[QUARTZ] EventTap active: selective F17/F18/F19 suppression enabled when Ableton Live is frontmost.")

    def on_press(self, key):
        try:
            if key in SHIFT_KEYS:
                self.shift_pressed = True
            elif key in CTRL_KEYS:
                self.ctrl_pressed = True
            elif key in CMD_KEYS:
                self.cmd_pressed = True
            elif key in OPT_KEYS:
                self.opt_pressed = True

            elif hasattr(key, 'vk') and key.vk in NUMPAD_VK_MAP:
                if self.ctrl_pressed:
                    cc_num, marker_idx = NUMPAD_VK_MAP[key.vk]
                    self._send_button_press(cc_num, f"NumPad {marker_idx} -> Marker {marker_idx}")

            elif key == keyboard.Key.f13:
                print("[ACTION] F13 Button -> Open Plugin Menu")
                subprocess.run(["open", "hammerspoon://pluginmenu"])
            elif key == keyboard.Key.f14:
                self._send_button_press(CC_BTN_F14, "F14 Button")
            elif key == keyboard.Key.f15:
                self._send_button_press(CC_BTN_F15, "F15 Button")
        except Exception as e:
            print(f"[ERROR] handling key press: {e}")

    def on_release(self, key):
        try:
            if key in SHIFT_KEYS:
                self.shift_pressed = False
            elif key in CTRL_KEYS:
                self.ctrl_pressed = False
            elif key in CMD_KEYS:
                self.cmd_pressed = False
            elif key in OPT_KEYS:
                self.opt_pressed = False

            elif hasattr(key, 'vk') and key.vk in NUMPAD_VK_MAP:
                cc_num, _ = NUMPAD_VK_MAP[key.vk]
                self._send_button_release(cc_num, "NumPad")

            elif key == keyboard.Key.f14:
                self._send_button_release(CC_BTN_F14, "F14 Button")
            elif key == keyboard.Key.f15:
                self._send_button_release(CC_BTN_F15, "F15 Button")
        except Exception:
            pass

    def _handle_knob_rotate(self, clockwise=True, modifiers=None):
        val = min(127, 64 + self.step_size) if clockwise else max(0, 64 - self.step_size)
        direction = "CW" if clockwise else "CCW"

        if modifiers is None:
            cmd, shift, ctrl, opt = self._get_live_modifiers()
        else:
            cmd, shift, ctrl, opt = modifiers

        if ctrl and shift:
            msg = mido.Message('control_change', channel=self.channel, control=CC_CUE_VOLUME, value=val)
            self.outport.send(msg)
            print(f"{direction} | Ctrl + Shift + Knob (Cue Volume) -> CC {CC_CUE_VOLUME} (Val {val})")

        elif cmd and shift:
            msg = mido.Message('control_change', channel=self.channel, control=CC_PAN, value=val)
            self.outport.send(msg)
            print(f"{direction} | CMD + Shift + Knob (Pan) -> CC {CC_PAN} (Val {val})")

        elif shift and not cmd and not ctrl and not opt:
            msg = mido.Message('control_change', channel=self.channel, control=CC_TIMELINE_SCRUB, value=val)
            self.outport.send(msg)
            print(f"{direction} | Shift + Knob (Timeline Scrub) -> CC {CC_TIMELINE_SCRUB} (Val {val})")

        elif cmd and not ctrl and not opt:
            msg = mido.Message('control_change', channel=self.channel, control=CC_VOLUME, value=val)
            self.outport.send(msg)
            print(f"{direction} | CMD + Knob (Volume) -> CC {CC_VOLUME} (Val {val})")

        elif ctrl and not cmd and not opt:
            msg = mido.Message('control_change', channel=self.channel, control=CC_DEVICE_NAV, value=val)
            self.outport.send(msg)
            print(f"{direction} | CTRL + Knob (Device Nav) -> CC {CC_DEVICE_NAV} (Val {val})")

        elif opt and not cmd and not ctrl and not shift:
            msg = mido.Message('control_change', channel=self.channel, control=CC_CLIP_GAIN, value=val)
            self.outport.send(msg)
            print(f"{direction} | Option + Knob (Clip Gain) -> CC {CC_CLIP_GAIN} (Val {val})")

        elif not cmd and not ctrl and shift == opt:
            step = 2 if shift else 1
            delta = step if clockwise else -step
            print(f"AI_KNOB {delta}", flush=True)

    def _send_button_press(self, cc, name):
        print(f"[BTN] {name} Pressed -> CC {cc} (127)")
        msg = mido.Message('control_change', channel=self.channel, control=cc, value=127)
        self.outport.send(msg)

    def _send_button_release(self, cc, name):
        msg = mido.Message('control_change', channel=self.channel, control=cc, value=0)
        self.outport.send(msg)

    def cleanup(self):
        self.running = False
        if self.tap_port:
            try:
                coregraphics.CGEventTapEnable(self.tap_port, False)
            except Exception:
                pass
        if self.run_loop and self.tap_source:
            try:
                corefoundation.CFRunLoopRemoveSource(self.run_loop, self.tap_source, kCFRunLoopCommonModes)
            except Exception:
                pass
        if self.tap_source:
            try:
                corefoundation.CFRelease(self.tap_source)
            except Exception:
                pass
            self.tap_source = None
        if self.tap_port:
            try:
                corefoundation.CFRelease(self.tap_port)
            except Exception:
                pass
            self.tap_port = None
        if hasattr(self, 'outport') and self.outport:
            try:
                self.outport.close()
            except Exception:
                pass

    def run(self):
        self.running = True
        self.worker_thread = threading.Thread(target=self._event_worker, daemon=True)
        self.worker_thread.start()

        self._init_quartz_tap()

        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )

        try:
            self.listener.start()
            print("[RUNNING] Event tap & MIDI bridge active. Press Ctrl+C to exit.")
            while self.listener.is_alive():
                corefoundation.CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.2, False)
        except KeyboardInterrupt:
            print("\n[STOPPING] Keychron MIDI Bridge terminating...")
        finally:
            self.running = False
            if self.listener and self.listener.is_alive():
                self.listener.stop()
            self.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Keychron Rotary Knob & NumPad to Virtual MIDI Bridge")
    parser.add_argument('--step', type=int, default=1, help="Step multiplier (default: 1)")
    parser.add_argument('--channel', type=int, default=16, help="MIDI Channel 1-16 (default: 16)")
    args = parser.parse_args()

    bridge = KeychronMidiBridge(step_size=args.step, channel=args.channel - 1)
    bridge.run()

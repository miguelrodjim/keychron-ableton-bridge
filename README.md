# Keychron Ableton Bridge

macOS daemon that captures Keychron K17 Max keystrokes (rotary knob, NumPad, function keys) and converts them into virtual MIDI CC messages for Ableton Live 12.

## How It Works

The bridge runs as a background process, listening for specific key events from the Keychron K17 Max keyboard. It translates these into MIDI CC messages on **Channel 16** and sends them to a virtual MIDI port that appears directly in Ableton Live.

## Control Map

| Gesture | MIDI CC | Action in Ableton |
| --- | --- | --- |
| Knob rotate | — | AI Knob under the pointer via Hammerspoon |
| Option + Shift + knob | — | Fine AI Knob via Hammerspoon |
| Ctrl + knob | 88 | Device navigation |
| Cmd + knob | 80 | Track volume |
| Cmd + Shift + knob | 85 | Track pan |
| Shift + knob | 89 | Timeline navigation |
| Option + knob | 90 | Gain of selected audio clips |
| Ctrl + Shift + knob | 104 | Cue volume |
| Knob click (F18) | 81 | Toggle plugin window |
| Shift + click | 87 | Toggle device on/off |
| Ctrl + Cmd + click | 103 | Cycle track monitoring |
| Ctrl + NumPad 0 | — | Add a locator via Hammerspoon |
| Ctrl + NumPad 1–9 | 91–99 | Jump to locator 1–9 in Arrangement order |
| F13 | — | Open the Hammerspoon plugin menu |
| F14 | 101 | Toggle metronome |
| F15 | 102 | Toggle Main track Mono via a Utility device |

The knob sends F17/F19 for rotation and F18 for a click. The bridge intercepts these knob events when Live is frontmost.

AI Knob rotation is sent directly to the matching [Hammerspoon configuration](https://github.com/miguelrodjim/les-macos-hammerspoon) that launches the bridge. Hammerspoon also handles Ctrl + NumPad 0 and F13. The remaining gestures use the virtual MIDI port.

## Requirements

- macOS 12+
- Python 3.10+
- Keychron K17 Max keyboard

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/miguelrodjim/keychron-ableton-bridge.git
   cd keychron-ableton-bridge
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

## Usage

### Manual Start

Double-click `Start_Keychron_MIDI.command` or run from terminal:

```bash
./Start_Keychron_MIDI.command
```

Or directly with Python:

```bash
./venv/bin/python bridge.py
```

### Command Line Options

```bash
./venv/bin/python bridge.py --step 2      # Step multiplier (default: 1)
./venv/bin/python bridge.py --channel 16  # MIDI channel 1-16 (default: 16)
```

### Auto-start with Ableton Live

See `examples/hammerspoon_auto_start.lua` for a Hammerspoon configuration that automatically starts the bridge when Ableton Live launches and stops it when Ableton closes.

## Setting Up in Ableton Live

1. Open Ableton Live
2. Go to Settings / Preferences (Cmd+,) > Link, Tempo & MIDI
3. Under Control Surface, select `AAKeychron_Live12` (install separately from [ableton-live-keychron-script](https://github.com/miguelrodjim/ableton-live-keychron-script))
4. Set Input to `Keychron K17 Max MIDI`
5. Set Output to `None`
6. Enable Track and Remote for the `Keychron K17 Max MIDI` input in the MIDI Ports table

## Architecture

- `bridge.py`: Main daemon. Uses `pynput` for key capture, `mido` for virtual MIDI output, and CoreGraphics for native scroll synthesis.
- `Start_Keychron_MIDI.command`: Double-click launcher that creates the venv and starts the bridge.
- `examples/hammerspoon_auto_start.lua`: Example Hammerspoon configuration for auto-start/stop.

## License

MIT License.

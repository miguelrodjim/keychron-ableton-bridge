# Keychron Ableton Bridge

macOS daemon that captures Keychron K17 Max keystrokes (rotary knob, NumPad, function keys) and converts them into virtual MIDI CC messages for Ableton Live 12.

## How It Works

The bridge runs as a background process, listening for specific key events from the Keychron K17 Max keyboard. It translates these into MIDI CC messages on **Channel 16** and sends them to a virtual MIDI port that appears directly in Ableton Live.

## Control Map

| Gesture | MIDI CC | Action in Ableton |
| :--- | :--- | :--- |
| Knob rotate | 86 | Track navigation (with native scroll) |
| CTRL + Knob | 88 | Device/plugin navigation |
| CMD + Knob | 80 | Track volume (0.5 dB steps) |
| CMD + Shift + Knob | 85 | Track pan (5 pt steps) |
| Shift + Knob | 89 | Timeline scrub |
| Click (F15) | 81 | Toggle plugin window |
| Shift + Click (F15) | 87 | Toggle device on/off (A/B test) |
| NumPad 1-9 | 91-99 | Jump to marker 1-9 |
| F17, F18, F19 | 82, 83, 84 | Free for custom mapping |

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

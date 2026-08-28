#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=========================================================="
echo "  🎹 Keychron K17 Max Rotary Knob -> Virtual MIDI Bridge  "
echo "=========================================================="
echo ""

if [ ! -d "$DIR/venv" ]; then
    echo "Creating virtual environment and installing dependencies..."
    python3 -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install mido python-rtmidi pynput
fi

echo "Starting MIDI Bridge..."
echo "Press Ctrl+C to stop."
echo ""

"$DIR/venv/bin/python" "$DIR/bridge.py" "$@"

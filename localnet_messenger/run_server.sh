#!/bin/bash
# LocalNet Messenger - Server Launcher Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting LocalNet Messenger Server..."
python server/server.py --host 0.0.0.0 --port 8765 "$@"

#!/bin/bash
# LocalNet Messenger - Client Launcher Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting LocalNet Messenger Client..."
python client/client.py "$@"

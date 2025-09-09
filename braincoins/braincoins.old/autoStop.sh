#!/usr/bin/bash

PROCESS_NAME="[t]ortoise-tts.*python"

if [[ ! $(pgrep -f "$PROCESS_NAME") ]]; then
    echo "Process $PROCESS_NAME is not running, shutting down server..."
    sudo shutdown -h now  # Replace with your preferred shutdown command
else
    echo "Process $PROCESS_NAME is alive, waiting..."
fi

exit 0

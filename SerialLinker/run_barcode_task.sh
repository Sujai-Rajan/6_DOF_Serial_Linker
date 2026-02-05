#!/bin/bash
# -----------------------------------------------------------
# Dynamsoft Barcode Task Client
# Equivalent to Windows .bat launcher
# Author: Sujai Rajan
# -----------------------------------------------------------

# Python script that talks to the task server
SCRIPT_PATH="/home/er/Documents/example.py"

# --- Windows-style UNC paths (use double backslashes escaped for bash) ---
# IMPORTANT: these are sent *as text* to the Windows server, not accessed locally.
FILE_PATH="\\\\hsv-dc2\\\\barcode_reader\\\\checker_line_3\\\\image\\\\2D_Barcode.jpg"
OUTPUT_PATH="/home/er/Desktop/barcode_result.txt"

# Run the Python client (connecting to 10.40.17.62:9000)
echo "[INFO] Starting Dynamsoft client..."
/usr/bin/python3 "$SCRIPT_PATH" "$FILE_PATH" "$OUTPUT_PATH"

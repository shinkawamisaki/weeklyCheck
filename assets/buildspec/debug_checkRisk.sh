#!/bin/bash
set -euo pipefail

echo "--- DEBUG WRAPPER: Starting checkRisk.sh ---"

# Print relevant environment variables before execution
echo "DEBUG: OPENAI_API_KEY=${OPENAI_API_KEY:-}"
echo "DEBUG: POLISH_WITH_OPENAI=${POLISH_WITH_OPENAI:-}"

# Execute the original checkRisk.sh script
# Capture its stdout and stderr separately
# The script itself will print its completion message to stdout
# The script will also call polish_with_openai which does its own curl

# Run the script and capture its output
# The script itself writes the report to output/checkRiskReport_*.md
# The script also prints a completion message to stdout

# We need to ensure the script's internal debug messages (from polish_with_openai) are visible
# and that its final completion message is also visible.

# Execute the original script. Its internal 'echo' statements will go to stdout.
# Its 'polish_with_openai' function will also print debugs to stdout/stderr.
# The script's final '✅ 完了: ...' message will also go to stdout.

bash ./checkRisk.sh

echo "--- DEBUG WRAPPER: checkRisk.sh finished ---"

# After checkRisk.sh runs, the report file should be in output/checkRiskReport_*.md
# The buildspec will then handle moving/copying this file.

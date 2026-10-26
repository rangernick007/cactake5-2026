#!/bin/bash
# Starts Collegia for the phone/laptop demo on the current Wi-Fi.
# Put GEMINI_API_KEY=... in a file named .env next to this script (it is git-ignored).
cd "$(dirname "$0")" || exit 1

if [ -f .env ]; then set -a; . ./.env; set +a; fi

PORT="${PORT:-5001}"
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"
if [ -z "$IP" ]; then
  echo "No Wi-Fi address found. Join the Wi-Fi first. Using 127.0.0.1 (this laptop only)."
  IP="127.0.0.1"
fi

# Stop any older copy on this port
lsof -ti ":$PORT" 2>/dev/null | xargs kill 2>/dev/null
sleep 1

export PORT HOST=0.0.0.0 PUBLIC_BASE_URL="http://$IP:$PORT"
[ -z "$GEMINI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ] && echo "Note: no AI key set, so AI Picks will not work. Add GEMINI_API_KEY=... to .env"
echo "Collegia on this laptop: http://127.0.0.1:$PORT"
echo "Collegia for phones on the same Wi-Fi: $PUBLIC_BASE_URL"
echo "Create events AFTER starting, so their QR codes use this address."
exec python3 app.py

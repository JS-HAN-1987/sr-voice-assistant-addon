#!/usr/bin/with-contenv bashio

echo "========================================"
echo "SR Voice Assistant + Chat UI 시작"
echo "========================================"

# Flask Chat UI 서버 백그라운드 실행
echo "[INFO] Flask Chat UI 서버 시작 (Port 9822)..."
python3 /app.py &
FLASK_PID=$!

# Wyoming STT 서버 백그라운드 실행
echo "[INFO] Wyoming STT 서버 시작 (Port 10300)..."
python3 /wyoming_stt.py &
STT_PID=$!

# Wyoming TTS 서버 실행 (포그라운드)
echo "[INFO] Wyoming TTS 서버 시작 (Port 10400)..."
python3 /wyoming_tts.py
TTS_EXIT_CODE=$?

# TTS가 종료되면 나머지도 함께 종료
kill $STT_PID 2>/dev/null
kill $FLASK_PID 2>/dev/null

exit $TTS_EXIT_CODE
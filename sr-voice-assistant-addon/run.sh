#!/usr/bin/with-contenv bashio

echo "========================================"
echo "SR Voice Assistant (Wyoming Only) 시작"
echo "========================================"

# Wyoming STT 서버 백그라운드 실행 
echo "[INFO] Wyoming STT 서버 시작 (Port 10300)..."
python3 /wyoming_stt.py &
STT_PID=$!

# Wyoming TTS 서버 실행 (포그라운드) 
echo "[INFO] Wyoming TTS 서버 시작 (Port 10400)..."
python3 /wyoming_tts.py
TTS_EXIT_CODE=$?

# TTS가 종료되면 STT도 함께 종료
kill $STT_PID 2>/dev/null

exit $TTS_EXIT_CODE
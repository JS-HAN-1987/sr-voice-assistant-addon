#!/usr/bin/with-contenv bashio

echo "========================================"
echo "SR Voice Assistant 서버 시작 중"
echo "========================================"

# Flask REST API 서버 백그라운드 실행
echo "[INFO] Flask API 서버 시작..."
python3 /app.py &
FLASK_PID=$!
echo "[INFO] Flask PID: $FLASK_PID"

# 잠깐 대기
sleep 2

# Wyoming STT 서버 백그라운드 실행
echo "[INFO] Wyoming STT 서버 시작..."
python3 /wyoming_stt.py &
STT_PID=$!
echo "[INFO] Wyoming STT PID: $STT_PID"

# 잠깐 대기
sleep 2

# Wyoming TTS 서버 실행 (포그라운드)
echo "[INFO] Wyoming TTS 서버 시작..."
python3 /wyoming_tts.py

# 에러 발생 시 처리
ERROR_CODE=$?
echo "[ERROR] Wyoming TTS 서버가 종료되었습니다. 에러 코드: $ERROR_CODE"

# 백그라운드 프로세스 종료
kill $FLASK_PID $STT_PID 2>/dev/null

exit $ERROR_CODE
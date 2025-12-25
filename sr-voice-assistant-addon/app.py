from flask import Flask, request, Response, send_file
from flask_cors import CORS
import speech_recognition as sr
from gtts import gTTS
import os
import json
import io
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Speech Recognition 초기화
recognizer = sr.Recognizer()

def json_response(data, status=200):
    """한글이 제대로 표시되는 JSON 응답"""
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype='application/json; charset=utf-8'
    )

def load_options():
    """애드온 옵션 로드"""
    options_file = "/data/options.json"
    if os.path.exists(options_file):
        try:
            with open(options_file, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"옵션 로드 실패: {e}", flush=True)
    
    # 기본값
    return {
        "api_port": 5007,
        "language": "ko-KR",
        "stt_wyoming_port": 10300,
        "tts_wyoming_port": 10400
    }

def get_ha_token():
    """Supervisor 토큰 가져오기"""
    token = os.environ.get('SUPERVISOR_TOKEN')
    if not token:
        print("[WARNING] SUPERVISOR_TOKEN이 없습니다.", flush=True)
    else:
        print(f"[INFO] SUPERVISOR_TOKEN 확인됨 (길이: {len(token)})", flush=True)
    return token

def update_ha_sensor(entity_id: str, state: str, attributes: dict = None):
    """Home Assistant 센서 상태 업데이트"""
    ha_url = "http://supervisor/core/api"
    token = get_ha_token()
    
    if not token:
        print(f"[WARNING] 토큰 없음 - 센서 업데이트 건너뜀: {entity_id}", flush=True)
        return False
    
    url = f"{ha_url}/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "state": state,
        "attributes": attributes or {}
    }
    
    try:
        print(f"[DEBUG] 센서 업데이트 시도: {entity_id}", flush=True)
        print(f"[DEBUG] URL: {url}", flush=True)
        print(f"[DEBUG] State: {state[:50] if len(state) > 50 else state}", flush=True)
        
        response = requests.post(url, json=data, headers=headers, timeout=5)
        
        print(f"[DEBUG] 응답 상태 코드: {response.status_code}", flush=True)
        
        if response.status_code in [200, 201]:
            print(f"[INFO] ✓ 센서 업데이트 성공: {entity_id}", flush=True)
            return True
        else:
            print(f"[ERROR] ✗ 센서 업데이트 실패: {entity_id}", flush=True)
            print(f"[ERROR] 상태 코드: {response.status_code}", flush=True)
            print(f"[ERROR] 응답 내용: {response.text}", flush=True)
            return False
    except Exception as e:
        print(f"[ERROR] ✗ 센서 업데이트 예외: {entity_id}", flush=True)
        print(f"[ERROR] 예외 내용: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False

def fire_ha_event(event_type: str, event_data: dict):
    """Home Assistant 이벤트 발생"""
    ha_url = "http://supervisor/core/api"
    token = get_ha_token()
    
    if not token:
        print(f"[WARNING] 토큰 없음 - 이벤트 발생 건너뜀: {event_type}", flush=True)
        return False
    
    url = f"{ha_url}/events/{event_type}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"[DEBUG] 이벤트 발생 시도: {event_type}", flush=True)
        
        response = requests.post(url, json=event_data, headers=headers, timeout=5)
        
        print(f"[DEBUG] 이벤트 응답 상태 코드: {response.status_code}", flush=True)
        
        if response.status_code in [200, 201]:
            print(f"[INFO] ✓ 이벤트 발생 성공: {event_type}", flush=True)
            return True
        else:
            print(f"[ERROR] ✗ 이벤트 발생 실패: {event_type}", flush=True)
            print(f"[ERROR] 응답: {response.text}", flush=True)
            return False
    except Exception as e:
        print(f"[ERROR] ✗ 이벤트 발생 예외: {event_type}, {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False

# ==================== STT 엔드포인트 ====================
@app.route('/stt', methods=['POST'])
def speech_to_text():
    """음성을 텍스트로 변환"""
    if 'file' not in request.files:
        return json_response({"error": "파일이 없습니다"}, 400)
    
    audio_file = request.files['file']
    options = load_options()
    language = options.get('language', 'ko-KR')
    
    try:
        with sr.AudioFile(audio_file) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language=language)
            
            timestamp = datetime.now().isoformat()
            
            # 1. Home Assistant 센서 업데이트
            update_ha_sensor(
                "sensor.voice_last_stt",
                text,
                {
                    "friendly_name": "마지막 음성 인식",
                    "icon": "mdi:microphone",
                    "timestamp": timestamp,
                    "language": language
                }
            )
            
            # 2. Home Assistant 이벤트 발생
            fire_ha_event("voice_stt", {
                "text": text,
                "timestamp": timestamp,
                "language": language
            })
            
            return json_response({
                "result": text,
                "timestamp": timestamp
            })
            
    except sr.UnknownValueError:
        return json_response({"error": "음성을 인식할 수 없습니다"}, 422)
    except sr.RequestError as e:
        return json_response({"error": f"Google 서비스 에러: {e}"}, 500)
    except Exception as e:
        return json_response({"error": f"서버 오류: {str(e)}"}, 500)

# ==================== TTS 엔드포인트 ====================
@app.route('/tts', methods=['POST'])
def text_to_speech():
    """텍스트를 음성으로 변환"""
    try:
        # JSON 또는 form-data에서 텍스트 가져오기
        if request.is_json:
            data = request.get_json()
            text = data.get('text', '')
            language = data.get('language')
        else:
            text = request.form.get('text', '')
            language = request.form.get('language')
        
        if not text:
            return json_response({"error": "텍스트가 없습니다"}, 400)
        
        # 언어 설정
        if not language:
            options = load_options()
            language = options.get('language', 'ko-KR')
            # gTTS는 'ko-KR' 대신 'ko' 사용
            if '-' in language:
                tts_lang = language.split('-')[0]
            else:
                tts_lang = language
        else:
            tts_lang = language
        
        timestamp = datetime.now().isoformat()
        
        # 1. Home Assistant 센서 업데이트
        update_ha_sensor(
            "sensor.voice_last_tts",
            text,
            {
                "friendly_name": "마지막 음성 출력",
                "icon": "mdi:speaker",
                "timestamp": timestamp,
                "language": tts_lang
            }
        )
        
        # 2. Home Assistant 이벤트 발생
        fire_ha_event("voice_tts", {
            "text": text,
            "timestamp": timestamp,
            "language": tts_lang
        })
        
        # 3. gTTS로 음성 생성
        tts = gTTS(text=text, lang=tts_lang, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        
        return send_file(
            audio_buffer,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name='speech.mp3'
        )
        
    except ValueError as e:
        return json_response({"error": f"지원하지 않는 언어입니다: {str(e)}"}, 400)
    except Exception as e:
        return json_response({"error": f"서버 오류: {str(e)}"}, 500)

# ==================== 상태 확인 ====================
@app.route('/health', methods=['GET'])
def health_check():
    """상태 확인"""
    return json_response({"status": "healthy"})

@app.route('/info', methods=['GET'])
def info():
    """애드온 정보"""
    options = load_options()
    return json_response({
        "name": "SR Voice Assistant",
        "version": "1.0.0",
        "api_port": options.get('api_port', 5007),
        "stt_wyoming_port": options.get('stt_wyoming_port', 10300),
        "tts_wyoming_port": options.get('tts_wyoming_port', 10400),
        "language": options.get('language', 'ko-KR'),
        "ha_integration": get_ha_token() is not None
    })

if __name__ == '__main__':
    options = load_options()
    api_port = options.get('api_port', 5007)
    
    print("=" * 60, flush=True)
    print(f"SR Voice Assistant 서버 시작", flush=True)
    print(f"REST API 포트: {api_port}", flush=True)
    print(f"STT Wyoming 포트: {options.get('stt_wyoming_port', 10300)}", flush=True)
    print(f"TTS Wyoming 포트: {options.get('tts_wyoming_port', 10400)}", flush=True)
    print(f"언어: {options.get('language', 'ko-KR')}", flush=True)
    token = get_ha_token()
    print(f"HA 통합: {'활성화' if token else '비활성화'}", flush=True)
    print("=" * 60, flush=True)
    
    # 시작 시 센서 초기화 테스트
    if token:
        print("\n[INFO] 센서 초기화 테스트 중...", flush=True)
        
        # 초기 센서 생성
        test_stt = update_ha_sensor(
            "sensor.voice_last_stt",
            "대기 중...",
            {
                "friendly_name": "마지막 음성 인식",
                "icon": "mdi:microphone",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        test_tts = update_ha_sensor(
            "sensor.voice_last_tts",
            "대기 중...",
            {
                "friendly_name": "마지막 음성 출력",
                "icon": "mdi:speaker",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        if test_stt and test_tts:
            print("[INFO] ✓ 센서 초기화 성공!", flush=True)
            print("[INFO] Home Assistant에서 다음 센서를 확인하세요:", flush=True)
            print("[INFO]   - sensor.voice_last_stt", flush=True)
            print("[INFO]   - sensor.voice_last_tts", flush=True)
        else:
            print("[WARNING] ✗ 센서 초기화 실패. 위 로그를 확인하세요.", flush=True)
        
        print("=" * 60, flush=True)
    else:
        print("\n[WARNING] SUPERVISOR_TOKEN이 없어 센서를 생성할 수 없습니다.", flush=True)
        print("[INFO] config.yaml에서 homeassistant_api: true 확인하세요.", flush=True)
        print("=" * 60, flush=True)
    
    print("\n[INFO] Flask 서버 시작 중...\n", flush=True)
    app.run(host='0.0.0.0', port=api_port, debug=False)

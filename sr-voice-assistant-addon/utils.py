# utils.py
import os
import json
import logging
import requests

_LOGGER = logging.getLogger(__name__)

def load_options():
    """애드온의 options.json 또는 환경 변수에서 설정 로드"""
    options_file = "/data/options.json"
    options = {
        "api_port": 5007,
        "language": "ko",
        "stt_wyoming_port": 10300,
        "tts_wyoming_port": 10400,
        "ha_ip": "http://homeassistant"
    }

    if os.path.exists(options_file):
        try:
            with open(options_file, "r") as f:
                options.update(json.load(f))
        except Exception as e:
            _LOGGER.error(f"옵션 파일 로드 실패: {e}")

    # 환경 변수 우선순위 (Supervisor 제공 토큰 등)
    token = os.environ.get('SR_VOICE_TOKEN') or options.get('api_token')
    return options, token

def fire_ha_event(event_type, event_data):
    # 이 로그가 찍히는지 확인하는 게 핵심입니다!
    print(f">>> [DEBUG] fire_ha_event 호출됨: {event_type}", flush=True)
    
    options, token = load_options()
    if not token:
        print(">>> [DEBUG] 에러: 토큰이 없습니다!", flush=True)
        return

    # IP 주소가 제대로 오는지 확인
    ha_ip = options.get('ha_ip', 'http://homeassistant')
    url = f"http://{ha_ip}:8123/api/events/{event_type}"
    
    try:
        r = requests.post(url, json=event_data, headers={"Authorization": f"Bearer {token}"}, timeout=2)
        print(f">>> [DEBUG] HA 응답 코드: {r.status_code}", flush=True)
    except Exception as e:
        print(f">>> [DEBUG] 전송 중 예외 발생: {e}", flush=True)
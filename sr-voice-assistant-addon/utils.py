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
        "language": "ko-KR",
        "stt_wyoming_port": 10300,
        "tts_wyoming_port": 10400,
        "ha_ip": "192.168.219.111"
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

def fire_ha_event(event_type: str, event_data: dict):
    """Home Assistant API를 통해 이벤트 발생"""
    options, token = load_options()
    ha_ip = options.get('ha_ip')
    
    if not token:
        _LOGGER.warning(f"토큰이 없어 이벤트를 건너뜁니다: {event_type}")
        return False

    url = f"http://{ha_ip}:8123/api/events/{event_type}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=event_data, headers=headers, timeout=5)
        if response.status_code in [200, 201]:
            _LOGGER.info(f"HA 이벤트 전송 성공: {event_type}")
            return True
    except Exception as e:
        _LOGGER.error(f"HA 이벤트 전송 오류: {e}")
    return False
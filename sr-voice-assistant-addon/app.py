from flask import Flask, request, Response, send_file
from flask_cors import CORS
import speech_recognition as sr
from gtts import gTTS
import os
import json
import io
import requests
from datetime import datetime
import paho.mqtt.client as mqtt
import time
import uuid

app = Flask(__name__)
CORS(app)

# Speech Recognition 초기화
recognizer = sr.Recognizer()

# MQTT 클라이언트 초기화
mqtt_client = None
mqtt_connected = False
mqtt_discovery_prefix = "homeassistant"  # 기본 discovery prefix

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
        "tts_wyoming_port": 10400,
        "mqtt_host": "core-mosquitto",
        "mqtt_port": 1883,
        "mqtt_user": "",
        "mqtt_password": "",
        "mqtt_discovery_prefix": "homeassistant"
    }

def init_mqtt():
    """MQTT 클라이언트 초기화 및 연결"""
    global mqtt_client, mqtt_connected, mqtt_discovery_prefix
    
    options = load_options()
    mqtt_host = options.get('mqtt_host', 'core-mosquitto')
    mqtt_port = int(options.get('mqtt_port', 1883))
    mqtt_user = options.get('mqtt_user', 'homeassistant')  # 기본값 변경
    mqtt_password = options.get('mqtt_password', '')
    mqtt_discovery_prefix = options.get('mqtt_discovery_prefix', 'homeassistant')
    
    
    print(f"[MQTT] 연결 설정:", flush=True)
    print(f"[MQTT]   호스트: {mqtt_host}", flush=True)
    print(f"[MQTT]   포트: {mqtt_port}", flush=True)
    print(f"[MQTT]   사용자: {mqtt_user}", flush=True)
    print(f"[MQTT]   비밀번호: {'설정됨' if mqtt_password else '없음'}", flush=True)

    # 고유한 client_id 생성
    client_id = f"sr_voice_assistant_{str(uuid.uuid4())[:8]}"
    
    def on_connect(client, userdata, flags, rc):
        global mqtt_connected
        if rc == 0:
            mqtt_connected = True
            print(f"[MQTT] ✓ 연결 성공: {mqtt_host}:{mqtt_port}", flush=True)
            
            # MQTT Discovery를 통해 센서 자동 등록
            register_mqtt_discovery()
            
            # 상태 온라인으로 설정
            client.publish(f"{mqtt_discovery_prefix}/status", "online", retain=True)
        else:
            mqtt_connected = False
            error_messages = {
                1: "잘못된 프로토콜 버전",
                2: "잘못된 클라이언트 식별자",
                3: "서버 사용 불가",
                4: "잘못된 사용자명 또는 비밀번호",
                5: "인증 실패"
            }
            print(f"[MQTT] ✗ 연결 실패: 코드 {rc} - {error_messages.get(rc, '알 수 없는 오류')}", flush=True)
    
    def on_disconnect(client, userdata, rc):
        global mqtt_connected
        mqtt_connected = False
        if rc != 0:
            print(f"[MQTT] 연결 끊김: 코드 {rc}", flush=True)
    
    mqtt_client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
    
    if mqtt_user and mqtt_password:
        mqtt_client.username_pw_set(mqtt_user, mqtt_password)
    
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    
    try:
        mqtt_client.connect(mqtt_host, mqtt_port, 60)
        mqtt_client.loop_start()
        
        # 연결 대기 (3초 타임아웃)
        for i in range(30):
            if mqtt_connected:
                break
            time.sleep(0.1)
        
        return mqtt_connected
    except Exception as e:
        print(f"[MQTT] ✗ 연결 시도 실패: {e}", flush=True)
        return False

def register_mqtt_discovery():
    """Home Assistant MQTT Discovery를 통해 센서 자동 등록"""
    if not mqtt_connected:
        return
    
    # 장치 정보 정의
    device = {
        "identifiers": ["sr_voice_assistant"],
        "name": "SR Voice Assistant",
        "manufacturer": "Custom",
        "model": "Voice Assistant v1.0",
        "sw_version": "1.0.0",
        "configuration_url": "https://github.com/your-repo/sr-voice-assistant"
    }
    
    # STT 센서 Discovery (sensor)
    stt_config = {
        "name": "Voice Last STT",
        "unique_id": "sr_voice_last_stt",
        "state_topic": "sr_voice/stt/state",
        "json_attributes_topic": "sr_voice/stt/attributes",
        "value_template": "{{ value_json.text if value_json is defined else value }}",
        "availability_topic": f"{mqtt_discovery_prefix}/status",
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device,
        "icon": "mdi:microphone",
        "has_entity_name": True,
        "origin": {
            "name": "SR Voice Assistant",
            "sw_version": "1.0.0",
            "support_url": "https://github.com/your-repo/sr-voice-assistant"
        },
        # 속성 표시 설정
        "json_attributes_template": "{{ value_json | tojson }}",
        "state_class": "measurement",
        "suggested_display_precision": 0
    }
    
    # TTS 센서 Discovery (sensor)
    tts_config = {
        "name": "Voice Last TTS",
        "unique_id": "sr_voice_last_tts",
        "state_topic": "sr_voice/tts/state",
        "json_attributes_topic": "sr_voice/tts/attributes",
        "value_template": "{{ value_json.text if value_json is defined else value }}",
        "availability_topic": f"{mqtt_discovery_prefix}/status",
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device,
        "icon": "mdi:speaker",
        "has_entity_name": True,
        "origin": {
            "name": "SR Voice Assistant",
            "sw_version": "1.0.0",
            "support_url": "https://github.com/your-repo/sr-voice-assistant"
        },
        # 속성 표시 설정
        "json_attributes_template": "{{ value_json | tojson }}",
        "state_class": "measurement",
        "suggested_display_precision": 0
    }
    
    try:
        # Discovery 메시지 발행
        stt_topic = f"{mqtt_discovery_prefix}/sensor/sr_voice_last_stt/config"
        tts_topic = f"{mqtt_discovery_prefix}/sensor/sr_voice_last_tts/config"
        
        print(f"[MQTT] 📡 Discovery 메시지 발행 =======================", flush=True)
        print(f"[MQTT]   STT 토픽: {stt_topic}", flush=True)
        print(f"[MQTT]   TTS 토픽: {tts_topic}", flush=True)
        
        mqtt_client.publish(stt_topic, json.dumps(stt_config, indent=2), retain=True)
        mqtt_client.publish(tts_topic, json.dumps(tts_config, indent=2), retain=True)
        
        print(f"[MQTT] ✅ Discovery 센서 등록 완료", flush=True)
        
    except Exception as e:
        print(f"[MQTT] ❌ Discovery 등록 실패: {e}", flush=True)

# publish_mqtt_sensor 함수 시작 부분에 추가
def publish_mqtt_sensor(entity_type: str, state: str, attributes: dict = None):
    """MQTT를 통해 센서 상태 발행"""
    global mqtt_connected
    
    print(f"[DEBUG] publish_mqtt_sensor 호출: {entity_type}", flush=True)
    print(f"[DEBUG] 상태값: {state}", flush=True)
    print(f"[DEBUG] 속성: {attributes}", flush=True)
    
    # MQTT 연결 상태 체크 및 재시도
    if not mqtt_connected:
        print(f"[MQTT] ⚠️ 연결되지 않음 - 재연결 시도", flush=True)
        init_mqtt()  # 재연결 시도
        
        # 잠시 대기
        time.sleep(0.5)
        
        if not mqtt_connected:
            print(f"[MQTT] ✗ 재연결 실패 - {entity_type} 상태 발행 건너뜀", flush=True)
            return False
    
    try:
        timestamp = datetime.now().isoformat()
        
        # 기본 속성 설정 - 더 많은 정보 추가
        base_attributes = {
            "timestamp": timestamp,
            "last_updated": timestamp,
            "friendly_name": "마지막 음성 인식" if entity_type == "stt" else "마지막 음성 출력",
            "icon": "mdi:microphone" if entity_type == "stt" else "mdi:speaker",
            "device_class": "text",
            "original_text": state,  # 원본 텍스트 저장
            "text_length": len(state),  # 텍스트 길이
            "language": attributes.get('language', 'ko-KR') if attributes else 'ko-KR'
        }
        
        if attributes:
            base_attributes.update(attributes)
        
        if entity_type == "stt":
            # STT 상태 발행
            state_topic = "sr_voice/stt/state"
            attr_topic = "sr_voice/stt/attributes"
            event_topic = "sr_voice/event/stt"
            
        elif entity_type == "tts":
            # TTS 상태 발행
            state_topic = "sr_voice/tts/state"
            attr_topic = "sr_voice/tts/attributes"
            event_topic = "sr_voice/event/tts"
        else:
            return False
        
        print(f"[MQTT] 📤 {entity_type.upper()} 발행 시작 ==========================", flush=True)
        print(f"[MQTT]   토픽: {state_topic}", flush=True)
        print(f"[MQTT]   상태값: {state}", flush=True)
        print(f"[MQTT]   속성 토픽: {attr_topic}", flush=True)
        print(f"[MQTT]   속성 데이터:", flush=True)
        for key, value in base_attributes.items():
            print(f"[MQTT]     {key}: {value}", flush=True)
        
        # 1. 상태 발행
        print(f"[MQTT]   → 상태 발행 중...", flush=True)
        mqtt_client.publish(state_topic, state, retain=True)
        print(f"[MQTT]   ✓ 상태 발행 완료", flush=True)
        
        # 2. 속성 발행
        print(f"[MQTT]   → 속성 발행 중...", flush=True)
        attr_json = json.dumps(base_attributes, ensure_ascii=False, indent=2)
        mqtt_client.publish(
            attr_topic,
            attr_json,
            retain=True
        )
        print(f"[MQTT]   ✓ 속성 발행 완료", flush=True)
        print(f"[MQTT]   속성 JSON:", flush=True)
        print(attr_json, flush=True)
        
        # 3. 이벤트 발행 (retain=False, 이벤트는 저장하지 않음)
        print(f"[MQTT]   → 이벤트 발행 중...", flush=True)
        event_data = {
            "text": state,
            "timestamp": timestamp,
            "type": entity_type,
            "language": base_attributes.get('language', 'ko-KR'),
            "text_length": len(state),
            "original_text": state,
            **{k: v for k, v in base_attributes.items() 
               if k not in ["timestamp", "last_updated", "friendly_name", "icon"]}
        }
        
        event_json = json.dumps(event_data, ensure_ascii=False, indent=2)
        mqtt_client.publish(
            event_topic,
            event_json,
            retain=False
        )
        print(f"[MQTT]   ✓ 이벤트 발행 완료", flush=True)
        print(f"[MQTT]   이벤트 토픽: {event_topic}", flush=True)
        
        print(f"[MQTT] ✅ {entity_type.upper()} 발행 완료 =======================", flush=True)
        print(f"[MQTT]   요약: '{state[:50]}{'...' if len(state) > 50 else ''}'", flush=True)
        return True
        
    except Exception as e:
        print(f"[MQTT] ❌ 상태 발행 실패: {e}", flush=True)
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
            
            print(f"[STT] 🎤 음성 인식 완료 ===========================", flush=True)
            print(f"[STT]   인식 텍스트: {text}", flush=True)
            print(f"[STT]   언어: {language}", flush=True)
            print(f"[STT]   텍스트 길이: {len(text)}", flush=True)
            print(f"[STT]   타임스탬프: {timestamp}", flush=True)
            
            # MQTT로 상태 발행
            mqtt_success = publish_mqtt_sensor(
                "stt",
                text,
                {
                    "friendly_name": "마지막 음성 인식",
                    "icon": "mdi:microphone",
                    "timestamp": timestamp,
                    "language": language,
                    "device_class": "text",
                    "source": "google_stt",
                    "recognition_type": "speech_to_text",
                    "text_display": text,  # 표시용 텍스트
                    "char_count": len(text),
                    "word_count": len(text.split()),
                    "processing_time": datetime.now().isoformat(),
                    "additional_info": {
                        "service": "Google Speech Recognition",
                        "confidence": "high",  # Google STT는 신뢰도 정보 제공 안함
                        "audio_format": audio_file.content_type if audio_file.content_type else "wav"
                    }
                }
            )
            
            if mqtt_success:
                print(f"[STT] ✅ MQTT 발행 성공", flush=True)
            else:
                print(f"[STT] ⚠️ MQTT 발행 실패, REST API로 폴백", flush=True)
                # REST API로 폴백
                update_ha_sensor(
                    "sensor.voice_last_stt",
                    text,
                    {
                        "friendly_name": "마지막 음성 인식",
                        "icon": "mdi:microphone",
                        "timestamp": timestamp,
                        "language": language,
                        "original_text": text,
                        "text_length": len(text)
                    }
                )
            
            print(f"[STT] ============================================", flush=True)
            
            return json_response({
                "result": text,
                "timestamp": timestamp,
                "language": language,
                "text_length": len(text),
                "mqtt_published": mqtt_success,
                "char_count": len(text),
                "word_count": len(text.split())
            })
            
    except sr.UnknownValueError:
        error_msg = "음성을 인식할 수 없습니다"
        print(f"[STT] ❌ 오류: {error_msg}", flush=True)
        return json_response({"error": error_msg}, 422)
    except sr.RequestError as e:
        error_msg = f"Google 서비스 에러: {e}"
        print(f"[STT] ❌ 오류: {error_msg}", flush=True)
        return json_response({"error": error_msg}, 500)
    except Exception as e:
        error_msg = f"서버 오류: {str(e)}"
        print(f"[STT] ❌ 오류: {error_msg}", flush=True)
        import traceback
        traceback.print_exc()
        return json_response({"error": error_msg}, 500)

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
        
        print(f"[TTS] 🔊 텍스트 변환 시작 ===========================", flush=True)
        print(f"[TTS]   입력 텍스트: {text}", flush=True)
        print(f"[TTS]   언어: {tts_lang}", flush=True)
        print(f"[TTS]   텍스트 길이: {len(text)}", flush=True)
        print(f"[TTS]   단어 수: {len(text.split())}", flush=True)
        
        # MQTT로 상태 발행
        mqtt_success = publish_mqtt_sensor(
            "tts",
            text,
            {
                "friendly_name": "마지막 음성 출력",
                "icon": "mdi:speaker",
                "timestamp": timestamp,
                "language": tts_lang,
                "device_class": "text",
                "source": "google_tts",
                "synthesis_type": "text_to_speech",
                "text_display": text,
                "char_count": len(text),
                "word_count": len(text.split()),
                "audio_language": tts_lang,
                "tts_engine": "gTTS (Google Text-to-Speech)",
                "additional_info": {
                    "service": "Google TTS",
                    "engine": "gTTS",
                    "speed": "normal",
                    "output_format": "mp3"
                }
            }
        )
        
        if mqtt_success:
            print(f"[TTS] ✅ MQTT 발행 성공", flush=True)
        else:
            print(f"[TTS] ⚠️ MQTT 발행 실패, REST API로 폴백", flush=True)
            # REST API로 폴백
            update_ha_sensor(
                "sensor.voice_last_tts",
                text,
                {
                    "friendly_name": "마지막 음성 출력",
                    "icon": "mdi:speaker",
                    "timestamp": timestamp,
                    "language": tts_lang,
                    "original_text": text,
                    "text_length": len(text)
                }
            )
        
        # gTTS로 음성 생성
        print(f"[TTS]   → 음성 생성 중...", flush=True)
        tts = gTTS(text=text, lang=tts_lang, slow=False)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        
        file_size = len(audio_buffer.getvalue())
        print(f"[TTS]   ✓ 음성 파일 생성 완료: {file_size} bytes", flush=True)
        
        print(f"[TTS] ============================================", flush=True)
        
        return send_file(
            audio_buffer,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name='speech.mp3'
        )
        
    except ValueError as e:
        error_msg = f"지원하지 않는 언어입니다: {str(e)}"
        print(f"[TTS] ❌ 오류: {error_msg}", flush=True)
        return json_response({"error": error_msg}, 400)
    except Exception as e:
        error_msg = f"서버 오류: {str(e)}"
        print(f"[TTS] ❌ 오류: {error_msg}", flush=True)
        import traceback
        traceback.print_exc()
        return json_response({"error": error_msg}, 500)

# ==================== 상태 확인 ====================
@app.route('/health', methods=['GET'])
def health_check():
    """상태 확인"""
    mqtt_status = "connected" if mqtt_connected else "disconnected"
    return json_response({
        "status": "healthy",
        "mqtt": mqtt_status,
        "timestamp": datetime.now().isoformat()
    })

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
        "mqtt": {
            "connected": mqtt_connected,
            "host": options.get('mqtt_host', 'core-mosquitto'),
            "port": options.get('mqtt_port', 1883),
            "discovery_prefix": mqtt_discovery_prefix
        }
    })

# ==================== MQTT 테스트 엔드포인트 ====================
@app.route('/mqtt-test', methods=['POST'])
def mqtt_test():
    """MQTT 연결 테스트"""
    try:
        if request.is_json:
            data = request.get_json()
            test_text = data.get('text', '테스트 메시지')
        else:
            test_text = request.form.get('text', '테스트 메시지')
        
        print(f"[MQTT-TEST] 테스트 시작: {test_text}", flush=True)
        
        # STT 테스트
        stt_success = publish_mqtt_sensor("stt", f"테스트: {test_text}", {
            "friendly_name": "마지막 음성 인식",
            "icon": "mdi:microphone",
            "timestamp": datetime.now().isoformat(),
            "test": True
        })
        
        # TTS 테스트
        tts_success = publish_mqtt_sensor("tts", f"테스트: {test_text}", {
            "friendly_name": "마지막 음성 출력",
            "icon": "mdi:speaker",
            "timestamp": datetime.now().isoformat(),
            "test": True
        })
        
        return json_response({
            "mqtt_connected": mqtt_connected,
            "stt_published": stt_success,
            "tts_published": tts_success,
            "test_text": test_text,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return json_response({"error": f"테스트 실패: {str(e)}"}, 500)

@app.route('/mqtt-status', methods=['GET'])
def mqtt_status():
    """MQTT 상태 확인"""
    return json_response({
        "connected": mqtt_connected,
        "discovery_prefix": mqtt_discovery_prefix,
        "timestamp": datetime.now().isoformat()
    })



@app.route('/debug/mqtt-test', methods=['POST'])
def debug_mqtt_test():
    """MQTT 디버그 테스트"""
    try:
        test_data = request.get_json() or {}
        test_text = test_data.get('text', '디버그 테스트 메시지')
        test_type = test_data.get('type', 'stt')  # 'stt' or 'tts'
        
        print(f"[DEBUG] 🔧 MQTT 테스트 시작 =========================", flush=True)
        print(f"[DEBUG]   테스트 텍스트: {test_text}", flush=True)
        print(f"[DEBUG]   테스트 타입: {test_type}", flush=True)
        print(f"[DEBUG]   MQTT 연결 상태: {mqtt_connected}", flush=True)
        
        # MQTT 연결 상태 출력
        if mqtt_client:
            print(f"[DEBUG]   MQTT 클라이언트 ID: {mqtt_client._client_id}", flush=True)
        
        # 테스트 발행
        result = publish_mqtt_sensor(
            test_type,
            test_text,
            {
                "test": True,
                "debug": True,
                "timestamp": datetime.now().isoformat(),
                "message": "디버그 테스트 메시지",
                "language": "ko-KR"
            }
        )
        
        print(f"[DEBUG]   발행 결과: {result}", flush=True)
        print(f"[DEBUG] ============================================", flush=True)
        
        return json_response({
            "success": result,
            "mqtt_connected": mqtt_connected,
            "test_text": test_text,
            "test_type": test_type,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return json_response({"error": f"디버그 테스트 실패: {str(e)}"}, 500)

if __name__ == '__main__':
    options = load_options()
    api_port = options.get('api_port', 5007)
    
    print("=" * 60, flush=True)
    print(f"SR Voice Assistant 서버 시작", flush=True)
    print(f"REST API 포트: {api_port}", flush=True)
    print(f"STT Wyoming 포트: {options.get('stt_wyoming_port', 10300)}", flush=True)
    print(f"TTS Wyoming 포트: {options.get('tts_wyoming_port', 10400)}", flush=True)
    print(f"언어: {options.get('language', 'ko-KR')}", flush=True)
    print("=" * 60, flush=True)
    
    # MQTT 초기화
    print("\n[INFO] MQTT 연결 시도 중...", flush=True)
    mqtt_success = init_mqtt()
    
    if mqtt_success:
        print("[INFO] ✓ MQTT 연결 및 센서 등록 완료!", flush=True)
        print("[INFO] Home Assistant에서 다음 센서를 확인하세요:", flush=True)
        print(f"[INFO]   - sensor.sr_voice_last_stt", flush=True)
        print(f"[INFO]   - sensor.sr_voice_last_tts", flush=True)
        
        # 초기 상태 설정 (MQTT로)
        time.sleep(2)  # MQTT 연결 안정화 대기
        initial_time = datetime.now().isoformat()
        
        publish_mqtt_sensor("stt", "대기 중...", {
            "friendly_name": "마지막 음성 인식",
            "icon": "mdi:microphone",
            "timestamp": initial_time,
            "device_class": "text"
        })
        
        publish_mqtt_sensor("tts", "대기 중...", {
            "friendly_name": "마지막 음성 출력",
            "icon": "mdi:speaker",
            "timestamp": initial_time,
            "device_class": "text"
        })
        
        print("[INFO] ✓ 초기 상태 설정 완료", flush=True)
    else:
        print("[WARNING] ✗ MQTT 연결 실패", flush=True)
        print("[INFO] REST API를 사용하여 센서 초기화...", flush=True)
        
        # MQTT 실패 시 REST API로 폴백
        token = get_ha_token()
        if token:
            update_ha_sensor(
                "sensor.voice_last_stt",
                "대기 중...",
                {
                    "friendly_name": "마지막 음성 인식",
                    "icon": "mdi:microphone",
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            update_ha_sensor(
                "sensor.voice_last_tts",
                "대기 중...",
                {
                    "friendly_name": "마지막 음성 출력",
                    "icon": "mdi:speaker",
                    "timestamp": datetime.now().isoformat()
                }
            )
            print("[INFO] ✓ REST API 센서 초기화 완료", flush=True)
        else:
            print("[WARNING] ✗ REST API도 사용 불가", flush=True)
    
    print("=" * 60, flush=True)
    print("\n[INFO] Flask 서버 시작 중...\n", flush=True)
    
    # 종료 시 정리 함수
    import atexit
    
    def cleanup():
        print("[INFO] 애플리케이션 종료 중...", flush=True)
        if mqtt_client:
            # 오프라인 상태 알림
            mqtt_client.publish(f"{mqtt_discovery_prefix}/status", "offline", retain=True)
            time.sleep(0.5)
            mqtt_client.loop_stop()
            print("[MQTT] 클라이언트 종료", flush=True)
    
    atexit.register(cleanup)
    
    app.run(host='0.0.0.0', port=api_port, debug=False)
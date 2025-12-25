#!/usr/bin/env python3
"""Wyoming Protocol wrapper for Google STT with MQTT"""
import asyncio
import logging
import speech_recognition as sr
import paho.mqtt.client as mqtt
import json
import os
import time
from datetime import datetime
from functools import partial
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info, Attribution, AsrProgram, AsrModel
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.asr import Transcribe, Transcript

_LOGGER = logging.getLogger(__name__)

# MQTT 클라이언트 전역 변수
mqtt_client = None
mqtt_connected = False

def init_mqtt():
    """MQTT 클라이언트 초기화"""
    global mqtt_client, mqtt_connected
    
    # MQTT 설정 (options.json에서 읽거나 기본값)
    mqtt_host = os.environ.get('MQTT_HOST', 'core-mosquitto')
    mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
    mqtt_user = os.environ.get('MQTT_USER', '')
    mqtt_password = os.environ.get('MQTT_PASSWORD', '')
    
    client_id = f"wyoming_stt_{int(time.time())}"
    
    def on_connect(client, userdata, flags, rc):
        global mqtt_connected
        if rc == 0:
            mqtt_connected = True
            _LOGGER.info(f"✓ MQTT 연결 성공: {mqtt_host}:{mqtt_port}")
        else:
            mqtt_connected = False
            _LOGGER.error(f"✗ MQTT 연결 실패: 코드 {rc}")
    
    def on_disconnect(client, userdata, rc):
        global mqtt_connected
        mqtt_connected = False
        if rc != 0:
            _LOGGER.warning(f"MQTT 연결 끊김: 코드 {rc}")
    
    mqtt_client = mqtt.Client(client_id=client_id)
    
    if mqtt_user and mqtt_password:
        mqtt_client.username_pw_set(mqtt_user, mqtt_password)
    
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    
    try:
        mqtt_client.connect(mqtt_host, mqtt_port, 60)
        mqtt_client.loop_start()
        
        # 연결 대기
        for i in range(30):
            if mqtt_connected:
                break
            time.sleep(0.1)
        
        return mqtt_connected
    except Exception as e:
        _LOGGER.error(f"MQTT 연결 시도 실패: {e}")
        return False

def publish_mqtt_stt(text: str, language: str = "ko-KR"):
    """STT 결과를 MQTT로 발행"""
    global mqtt_connected
    
    if not mqtt_connected:
        _LOGGER.warning("MQTT 연결되지 않음 - STT 결과 발행 건너뜀")
        return False
    
    try:
        timestamp = datetime.now().isoformat()
        
        # 상태 발행
        state_topic = "sr_voice/stt/state"
        mqtt_client.publish(state_topic, text, retain=True)
        
        # 속성 발행
        attributes = {
            "friendly_name": "마지막 음성 인식",
            "icon": "mdi:microphone",
            "timestamp": timestamp,
            "language": language,
            "device_class": "text",
            "original_text": text,
            "text_length": len(text),
            "char_count": len(text),
            "word_count": len(text.split()),
            "source": "google_stt",
            "recognition_type": "speech_to_text"
        }
        
        attr_topic = "sr_voice/stt/attributes"
        mqtt_client.publish(
            attr_topic,
            json.dumps(attributes, ensure_ascii=False),
            retain=True
        )
        
        # 이벤트 발행
        event_data = {
            "text": text,
            "timestamp": timestamp,
            "type": "stt",
            "language": language,
            "text_length": len(text)
        }
        
        event_topic = "sr_voice/event/stt"
        mqtt_client.publish(
            event_topic,
            json.dumps(event_data, ensure_ascii=False),
            retain=False
        )
        
        _LOGGER.info(f"✓ STT 결과 MQTT 발행: {text[:50]}...")
        return True
        
    except Exception as e:
        _LOGGER.error(f"✗ STT MQTT 발행 실패: {e}")
        return False

class GoogleSttEventHandler(AsyncEventHandler):
    """Wyoming event handler for Google STT"""

    def __init__(self, *args, language="ko-KR", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        self.recognizer = sr.Recognizer()
        self.audio_buffer = bytearray()
        self.is_receiving = False

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(
                Info(
                    asr=[
                        AsrProgram(
                            name="google_stt",
                            description="Google Speech Recognition",
                            attribution=Attribution(
                                name="Google",
                                url="https://cloud.google.com/speech-to-text"
                            ),
                            installed=True,
                            version="1.0",
                            models=[
                                AsrModel(
                                    name="google_web",
                                    description="Google Web Speech API",
                                    attribution=Attribution(
                                        name="Google",
                                        url="https://cloud.google.com/speech-to-text"
                                    ),
                                    installed=True,
                                    languages=["ko-KR", "en-US", "ja-JP", "zh-CN"],
                                    version="1.0"
                                )
                            ],
                        )
                    ]
                ).event()
            )
            return True

        if AudioStart.is_type(event.type):
            self.is_receiving = True
            self.audio_buffer = bytearray()
            _LOGGER.debug("오디오 수신 시작")
            return True

        if AudioChunk.is_type(event.type):
            if self.is_receiving:
                chunk = AudioChunk.from_event(event)
                self.audio_buffer.extend(chunk.audio)
            return True

        if AudioStop.is_type(event.type):
            self.is_receiving = False
            _LOGGER.debug(f"오디오 수신 완료: {len(self.audio_buffer)} bytes")
            
            text = await self._recognize_speech()
            
            # MQTT로 결과 발행
            if text:
                publish_mqtt_stt(text, self.language)
            
            await self.write_event(
                Transcript(text=text).event()
            )
            _LOGGER.info(f"인식 결과: {text}")
            return True

        if Transcribe.is_type(event.type):
            _LOGGER.debug("Transcribe 요청")
            return True

        return True

    async def _recognize_speech(self) -> str:
        """음성 인식 (블로킹 작업을 비동기로)"""
        loop = asyncio.get_event_loop()
        
        try:
            audio_data = sr.AudioData(bytes(self.audio_buffer), 16000, 2)
            text = await loop.run_in_executor(
                None,
                partial(
                    self.recognizer.recognize_google,
                    audio_data,
                    language=self.language
                )
            )
            return text
        except sr.UnknownValueError:
            _LOGGER.warning("음성을 인식할 수 없습니다")
            return ""
        except sr.RequestError as e:
            _LOGGER.error(f"Google 서비스 에러: {e}")
            return ""
        except Exception as e:
            _LOGGER.error(f"인식 오류: {e}")
            return ""

async def main():
    """메인 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s'
    )
    
    # 설정
    host = "0.0.0.0"
    port = 10300
    language = "ko-KR"
    
    # MQTT 초기화
    _LOGGER.info("MQTT 초기화 중...")
    mqtt_init_success = init_mqtt()
    
    if mqtt_init_success:
        _LOGGER.info("✓ MQTT 초기화 완료")
    else:
        _LOGGER.warning("⚠️ MQTT 초기화 실패 - STT 결과는 MQTT로 발행되지 않음")
    
    try:
        _LOGGER.info("=" * 50)
        _LOGGER.info("Google STT Wyoming 서버 시작")
        _LOGGER.info(f"주소: {host}:{port}")
        _LOGGER.info(f"언어: {language}")
        _LOGGER.info(f"MQTT: {'활성화' if mqtt_connected else '비활성화'}")
        _LOGGER.info("=" * 50)
        
        server = AsyncServer.from_uri(f"tcp://{host}:{port}")
        
        _LOGGER.info("서버 리스닝 중...")
        await server.run(
            partial(GoogleSttEventHandler, language=language)
        )
    except Exception as e:
        _LOGGER.error(f"서버 시작 실패: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n서버 종료됨")
    except Exception as e:
        print(f"치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
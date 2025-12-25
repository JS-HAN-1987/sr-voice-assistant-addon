#!/usr/bin/env python3
"""Wyoming Protocol wrapper for Google TTS with MQTT"""
import asyncio
import logging
import io
import paho.mqtt.client as mqtt
import json
import os
import time
from datetime import datetime
from gtts import gTTS
from functools import partial
from wyoming.info import Describe, Info, Attribution, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event

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
    
    client_id = f"wyoming_tts_{int(time.time())}"
    
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

def publish_mqtt_tts(text: str, language: str = "ko"):
    """TTS 결과를 MQTT로 발행"""
    global mqtt_connected
    
    if not mqtt_connected:
        _LOGGER.warning("MQTT 연결되지 않음 - TTS 결과 발행 건너뜀")
        return False
    
    try:
        timestamp = datetime.now().isoformat()
        
        # 상태 발행
        state_topic = "sr_voice/tts/state"
        mqtt_client.publish(state_topic, text, retain=True)
        
        # 속성 발행
        attributes = {
            "friendly_name": "마지막 음성 출력",
            "icon": "mdi:speaker",
            "timestamp": timestamp,
            "language": language,
            "device_class": "text",
            "original_text": text,
            "text_length": len(text),
            "char_count": len(text),
            "word_count": len(text.split()),
            "source": "google_tts",
            "synthesis_type": "text_to_speech",
            "tts_engine": "gTTS (Google Text-to-Speech)"
        }
        
        attr_topic = "sr_voice/tts/attributes"
        mqtt_client.publish(
            attr_topic,
            json.dumps(attributes, ensure_ascii=False),
            retain=True
        )
        
        # 이벤트 발행
        event_data = {
            "text": text,
            "timestamp": timestamp,
            "type": "tts",
            "language": language,
            "text_length": len(text)
        }
        
        event_topic = "sr_voice/event/tts"
        mqtt_client.publish(
            event_topic,
            json.dumps(event_data, ensure_ascii=False),
            retain=False
        )
        
        _LOGGER.info(f"✓ TTS 결과 MQTT 발행: {text[:50]}...")
        return True
        
    except Exception as e:
        _LOGGER.error(f"✗ TTS MQTT 발행 실패: {e}")
        return False

class GoogleTtsEventHandler(AsyncEventHandler):
    """Wyoming event handler for Google TTS"""

    def __init__(self, *args, language="ko", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(
                Info(
                    tts=[
                        TtsProgram(
                            name="google_tts",
                            description="Google Text-to-Speech",
                            attribution=Attribution(
                                name="Google",
                                url="https://gtts.readthedocs.io/"
                            ),
                            installed=True,
                            version="1.0",
                            voices=[
                                TtsVoice(
                                    name="ko",
                                    description="Korean",
                                    attribution=Attribution(
                                        name="Google",
                                        url="https://gtts.readthedocs.io/"
                                    ),
                                    installed=True,
                                    languages=["ko", "ko-KR"],
                                    version="1.0"
                                ),
                                TtsVoice(
                                    name="en",
                                    description="English",
                                    attribution=Attribution(
                                        name="Google",
                                        url="https://gtts.readthedocs.io/"
                                    ),
                                    installed=True,
                                    languages=["en", "en-US"],
                                    version="1.0"
                                ),
                                TtsVoice(
                                    name="ja",
                                    description="Japanese",
                                    attribution=Attribution(
                                        name="Google",
                                        url="https://gtts.readthedocs.io/"
                                    ),
                                    installed=True,
                                    languages=["ja", "ja-JP"],
                                    version="1.0"
                                ),
                                TtsVoice(
                                    name="zh-CN",
                                    description="Chinese (Simplified)",
                                    attribution=Attribution(
                                        name="Google",
                                        url="https://gtts.readthedocs.io/"
                                    ),
                                    installed=True,
                                    languages=["zh-CN"],
                                    version="1.0"
                                ),
                            ],
                        )
                    ]
                ).event()
            )
            return True

        if Synthesize.is_type(event.type):
            synthesize = Synthesize.from_event(event)
            _LOGGER.info(f"텍스트 변환 요청: {synthesize.text}")
            
            voice = synthesize.voice
            if voice and voice.name:
                language = voice.name
            else:
                language = self.language
            
            # MQTT로 결과 발행 (음성 생성 전에)
            publish_mqtt_tts(synthesize.text, language)
            
            audio_data = await self._synthesize_speech(synthesize.text, language)
            
            if audio_data:
                await self.write_event(
                    AudioStart(
                        rate=22050,
                        width=2,
                        channels=1
                    ).event()
                )
                
                chunk_size = 1024
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i + chunk_size]
                    await self.write_event(
                        AudioChunk(
                            audio=chunk,
                            rate=22050,
                            width=2,
                            channels=1
                        ).event()
                    )
                
                await self.write_event(AudioStop().event())
                
                _LOGGER.info(f"음성 합성 완료: {len(audio_data)} bytes")
            else:
                _LOGGER.error("음성 합성 실패")
            
            return True

        return True

    async def _synthesize_speech(self, text: str, language: str) -> bytes:
        """텍스트를 음성으로 변환"""
        loop = asyncio.get_event_loop()
        
        try:
            audio_bytes = await loop.run_in_executor(
                None,
                partial(self._create_audio, text, language)
            )
            return audio_bytes
        except Exception as e:
            _LOGGER.error(f"음성 합성 오류: {e}")
            return b""

    def _create_audio(self, text: str, language: str) -> bytes:
        """gTTS로 음성 생성"""
        try:
            tts = gTTS(text=text, lang=language, slow=False)
            mp3_buffer = io.BytesIO()
            tts.write_to_fp(mp3_buffer)
            mp3_buffer.seek(0)
            
            audio_data = mp3_buffer.read()
            
            return audio_data
        except Exception as e:
            _LOGGER.error(f"오디오 생성 오류: {e}")
            return b""

async def main():
    """메인 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s'
    )
    
    # 설정
    host = "0.0.0.0"
    port = 10400
    language = "ko"
    
    # MQTT 초기화
    _LOGGER.info("MQTT 초기화 중...")
    mqtt_init_success = init_mqtt()
    
    if mqtt_init_success:
        _LOGGER.info("✓ MQTT 초기화 완료")
    else:
        _LOGGER.warning("⚠️ MQTT 초기화 실패 - TTS 결과는 MQTT로 발행되지 않음")
    
    try:
        _LOGGER.info("=" * 50)
        _LOGGER.info("Google TTS Wyoming 서버 시작")
        _LOGGER.info(f"주소: {host}:{port}")
        _LOGGER.info(f"언어: {language}")
        _LOGGER.info(f"MQTT: {'활성화' if mqtt_connected else '비활성화'}")
        _LOGGER.info("=" * 50)
        
        server = AsyncServer.from_uri(f"tcp://{host}:{port}")
        
        _LOGGER.info("서버 리스닝 중...")
        await server.run(
            partial(GoogleTtsEventHandler, language=language)
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
#!/usr/bin/env python3
"""Wyoming Protocol wrapper for Google TTS"""
import asyncio
import logging
import io
from gtts import gTTS
from functools import partial
from wyoming.info import Describe, Info, Attribution, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from utils import fire_ha_event, load_options

_LOGGER = logging.getLogger(__name__)


class GoogleTtsEventHandler(AsyncEventHandler):
    """Wyoming event handler for Google TTS"""

    def __init__(self, *args, language="ko", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            print(">>> [TYPE] Describe 요청 받음", flush=True)
            # 서버 정보 응답
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
            # 텍스트를 음성으로 변환
            synthesize = Synthesize.from_event(event)
            _LOGGER.info(f"TTS 요청 수신: {synthesize.text}")

            # 2. 이벤트 발생 (루프를 방해하지 않게 백그라운드로 뺌)
            try:
                loop = asyncio.get_running_loop()
                # executor를 사용해야 requests.post가 음성 합성을 방해하지 않습니다.
                loop.run_in_executor(None, fire_ha_event, "voice_tts", {"text": synthesize.text})
            except Exception as e:
                _LOGGER.error(f"이벤트 발생 코드 에러: {e}")
            
            # 언어 설정
            voice = synthesize.voice
            if voice and voice.name:
                language = voice.name
            else:
                language = self.language

            # 🔥 gTTS 호환 언어로 정규화
            LANGUAGE_MAP = {
                "ko-KR": "ko",
                "ko": "ko",
                "en-US": "en",
                "en": "en",
                "ja-JP": "ja",
                "ja": "ja",
            }

            language = LANGUAGE_MAP.get(language, self.language)
            
            # 비동기로 음성 합성 실행
            audio_data = await self._synthesize_speech(synthesize.text, language)
            
            if audio_data:
                # 오디오 시작 이벤트
                await self.write_event(
                    AudioStart(
                        rate=22050,  # gTTS는 22050Hz 사용
                        width=2,     # 16-bit
                        channels=1   # mono
                    ).event()
                )
                
                # 오디오 데이터를 청크로 전송
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
                
                # 오디오 종료 이벤트
                await self.write_event(AudioStop().event())
                
                _LOGGER.info(f"음성 합성 완료: {len(audio_data)} bytes")
            else:
                _LOGGER.error("음성 합성 실패")
            
            return True
        # 위 조건들에 해당하지 않는 나머지 이벤트들
        else:
            print(f">>> [TYPE] 알 수 없는 이벤트: {event.type}", flush=True)
            # 여기서 event.data 등을 찍어보면 더 자세한 정보를 알 수 있습니다.

        return True

    async def _synthesize_speech(self, text: str, language: str) -> bytes:
        """음성 합성 (블로킹 작업을 비동기로)"""
        loop = asyncio.get_event_loop()
        
        try:
            # gTTS로 음성 생성 (비동기 실행)
            audio_bytes = await loop.run_in_executor(
                None,
                partial(self._create_audio, text, language)
            )
            return audio_bytes
        except Exception as e:
            _LOGGER.error(f"음성 합성 오류: {e}")
            return b""

    def _create_audio(self, text: str, language: str) -> bytes:
        """실제 음성 생성 함수 (동기)"""
        try:
            # gTTS로 MP3 생성
            tts = gTTS(text=text, lang=language, slow=False)
            mp3_buffer = io.BytesIO()
            tts.write_to_fp(mp3_buffer)
            mp3_buffer.seek(0)
            
            # MP3 raw bytes 반환
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
    
    try:
        _LOGGER.info("=" * 50)
        _LOGGER.info("Google TTS Wyoming 서버 시작")
        _LOGGER.info(f"주소: {host}:{port}")
        _LOGGER.info(f"언어: {language}")
        _LOGGER.info("=" * 50)
        
        # 서버 시작
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
#    logging.basicConfig(
#        level=logging.DEBUG, # INFO에서 DEBUG로 변경
#        format='[%(levelname)s] %(message)s'
#    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n서버 종료됨")
    except Exception as e:
        print(f"치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
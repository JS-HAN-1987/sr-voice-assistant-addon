#!/usr/bin/env python3
"""Wyoming Protocol wrapper for Google STT"""
import asyncio
import logging
import speech_recognition as sr
from functools import partial
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info, Attribution, AsrProgram, AsrModel
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.asr import Transcribe, Transcript

_LOGGER = logging.getLogger(__name__)


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
            # 서버 정보 응답
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
            # 오디오 수신 시작
            self.is_receiving = True
            self.audio_buffer = bytearray()
            _LOGGER.debug("오디오 수신 시작")
            return True

        if AudioChunk.is_type(event.type):
            # 오디오 데이터 수신
            if self.is_receiving:
                chunk = AudioChunk.from_event(event)
                self.audio_buffer.extend(chunk.audio)
            return True

        if AudioStop.is_type(event.type):
            # 오디오 수신 완료, 인식 시작
            self.is_receiving = False
            _LOGGER.debug(f"오디오 수신 완료: {len(self.audio_buffer)} bytes")
            
            # 비동기로 음성 인식 실행
            text = await self._recognize_speech()
            
            # 결과 전송
            await self.write_event(
                Transcript(text=text).event()
            )
            _LOGGER.info(f"인식 결과: {text}")
            return True

        if Transcribe.is_type(event.type):
            # 직접 전사 요청
            _LOGGER.debug("Transcribe 요청")
            return True

        return True

    async def _recognize_speech(self) -> str:
        """음성 인식 (블로킹 작업을 비동기로)"""
        loop = asyncio.get_event_loop()
        
        try:
            # speech_recognition 라이브러리는 동기 함수이므로 executor에서 실행
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
    
    try:
        _LOGGER.info("=" * 50)
        _LOGGER.info("Google STT Wyoming 서버 시작")
        _LOGGER.info(f"주소: {host}:{port}")
        _LOGGER.info(f"언어: {language}")
        _LOGGER.info("=" * 50)
        
        # 서버 시작
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
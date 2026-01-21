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

_LOGGER = logging.getLogger(__name__)

import socket
import math
import re
import json
import numpy as np

# --- Blossom Robot Control Logic ---

class RotationTransformer:
    def __init__(self):
        # a, b, c Axis Angles (Radians)
        angles = np.radians([0, 120, 240])

        # Basis Vectors (3x3 Matrix)
        # Each row is x, y, z component of a, b, c vectors
        # z component is 1.0 to ensure Yaw moves all motors
        self.basis_vectors = np.array([
            [np.cos(theta), np.sin(theta), 1.0] for theta in angles
        ])

    def rpy_to_abc_rotation(self, roll, pitch, yaw):
        """Global RPY to Local ABC rotation (Degrees)"""
        # Global Rotation Vector
        global_rotation_vec = np.array([roll, pitch, yaw])

        # Matrix Multiplication
        abc_rotations = self.basis_vectors @ global_rotation_vec
        return abc_rotations[0], abc_rotations[1], abc_rotations[2]

class BlossomController:
    def __init__(self, host="esp32-voice.local", port=5005):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.transformer = RotationTransformer()
        self._stop_event = asyncio.Event()

    def send_cmd(self, m1, m2, m3, m4):
        """Send raw motor angles via UDP"""
        msg = f"{m1:.2f},{m2:.2f},{m3:.2f},{m4:.2f}"
        try:
            self.sock.sendto(msg.encode(), (self.host, self.port))
            # _LOGGER.debug(f"Sent UDP: {msg}")
        except Exception as e:
            _LOGGER.error(f"UDP Send Error: {e}")

    async def run_sequence(self, actions):
        """
        Execute a sequence of actions.
        actions: list of dicts [{'r':.., 'p':.., ..}, ...]
        """
        self._stop_event.clear()
        _LOGGER.info(f"Starting Robot Sequence: {len(actions)} steps")
        
        try:
            for i, action in enumerate(actions):
                if self._stop_event.is_set():
                    break
                
                r = float(action.get('r', 0))
                p = float(action.get('p', 0))
                y = float(action.get('y', 0))
                ear = float(action.get('a', 0)) # Ear angle
                delay = float(action.get('d', 0.5))

                # Calculate Motor Angles
                m1, m2, m3 = self.transformer.rpy_to_abc_rotation(r, p, y)
                
                # Send Command
                self.send_cmd(m1, m2, m3, ear)
                
                # Delay (Async)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                    # If wait returns without timeout, it means stop_event was set
                    break
                except asyncio.TimeoutError:
                    # Timeout reached, continue to next step
                    pass
                    
        except Exception as e:
            _LOGGER.error(f"Sequence Error: {e}")
        finally:
            _LOGGER.info("Robot Sequence Ended")
            # Optional: Return to neutral? User said "stop immediately", sticking to last position might be cleaner or neutral.
            # But the prompt says "동작은 멈춰야 해. 동작이 남아 있더라도."
            # It implies stopping the *sequence*, not necessarily resetting.
            pass

    def stop(self):
        self._stop_event.set()

# Global Controller Instance
robot_controller = BlossomController()



class GoogleTtsEventHandler(AsyncEventHandler):
    """Wyoming event handler for Google TTS"""

    def __init__(self, *args, language="ko", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language

    async def handle_event(self, event: Event) -> bool:
        _LOGGER.info(
            f"[EVENT] type={event.type} data={event.data if hasattr(event, 'data') else event}"
        )

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
            text = synthesize.text
            _LOGGER.info(f"TTS 요청 수신: {text}")

            # --- Check for Robot Control JSON ---
            # Format: [{"r":0,"p":10...}, ...] Text...
            robot_action_task = None
            
            # Regex to find JSON array at start
            # Matches [ ... ] possibly spanning lines, allowing nested braces if needed but simple is best
            # Use non-greedy match for the content inside
            match = re.match(r'^\s*(\[.*?\])(.*)', text, re.DOTALL)
            
            if match:
                json_str = match.group(1)
                text_content = match.group(2).strip()
                
                try:
                    actions = json.loads(json_str)
                    _LOGGER.info(f"Robot Actions Found: {len(actions)} steps")
                    
                    # Start Robot Task
                    robot_action_task = asyncio.create_task(robot_controller.run_sequence(actions))
                    
                    # Update text to speak (remove JSON)
                    text = text_content
                    if not text:
                        text = " " # Prevent empty text error
                        
                except json.JSONDecodeError:
                    _LOGGER.warning("Failed to parse Robot JSON, treating as text")
                except Exception as e:
                    _LOGGER.error(f"Robot processing error: {e}")

            # 언어 설정

            
            # 언어 설정
            voice = synthesize.voice
            if voice and voice.name:
                language = voice.name
            else:
                language = self.language

            # gTTS 호환 언어로 정규화
            LANGUAGE_MAP = {
                "ko-KR": "ko",
                "ko": "ko",
                "en-US": "en",
                "en": "en",
                "ja-JP": "ja",
                "ja": "ja",
            }

            language = LANGUAGE_MAP.get(language, self.language)
            
            # 음성 합성 실행
            audio_data = await self._synthesize_speech(text, language)
            
            if audio_data:
                # 오디오 시작 이벤트
                await self.write_event(
                    AudioStart(
                        rate=22050,
                        width=2,
                        channels=1
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
                
                # Stop Robot if still running
                if robot_action_task:
                     robot_controller.stop()
                     try:
                         await robot_action_task
                     except:
                         pass

                _LOGGER.info(f"음성 합성 완료: {len(audio_data)} bytes")
            else:
                _LOGGER.error("음성 합성 실패")
            
            return True





        return True

    async def _synthesize_speech(self, text: str, language: str) -> bytes:
        """음성 합성 (블로킹 작업을 비동기로)"""
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
        """실제 음성 생성 함수 (동기)"""
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
    

    host = "0.0.0.0"
    port = 10400
    language = "ko"
    
    try:
        _LOGGER.info("=" * 50)
        _LOGGER.info("Google TTS Wyoming 서버 시작")
        _LOGGER.info(f"주소: {host}:{port}")
        _LOGGER.info(f"언어: {language}")
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
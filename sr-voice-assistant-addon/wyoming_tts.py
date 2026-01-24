#!/usr/bin/env python3
"""Wyoming Protocol wrapper for Google TTS"""
import asyncio
import logging
import io
import os
from gtts import gTTS
from functools import partial
from wyoming.info import Describe, Info, Attribution, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
_LOGGER = logging.getLogger(__name__)
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
    """Robot controller using Home Assistant ESPHome API"""
    
    def __init__(self):
        self.ha_url = os.getenv("SUPERVISOR_API", "http://supervisor/core")
        self.ha_token = os.getenv("SUPERVISOR_TOKEN", "")
        self.transformer = RotationTransformer()
        self._stop_event = asyncio.Event()
        _LOGGER.info(f"Initialized BlossomController (HA API Mode)")

    async def send_cmd(self, m1, m2, m3, m4):
        """Send motor angles via Home Assistant ESPHome service"""
        import aiohttp
        
        service_url = f"{self.ha_url}/api/services/esphome/esp32_voice_set_motors"
        headers = {
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json"
        }
        data = {"m1": float(m1), "m2": float(m2), "m3": float(m3), "m4": float(m4)}
        
        _LOGGER.info(f"Calling HA API: {service_url}")
        _LOGGER.info(f"Motor data: {data}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(service_url, json=data, headers=headers) as resp:
                    resp_text = await resp.text()
                    _LOGGER.info(f"HA API Response: {resp.status} - {resp_text[:200]}")
                    if resp.status != 200:
                        _LOGGER.error(f"HA API Error: {resp.status} - {resp_text}")
        except Exception as e:
            _LOGGER.error(f"HA API Send Error: {e}")

    async def run_sequence(self, actions):
        """Execute a sequence of actions."""
        self._stop_event.clear()
        _LOGGER.info(f"Starting Robot Sequence: {len(actions)} steps")
        
        try:
            for i, action in enumerate(actions):
                if self._stop_event.is_set():
                    break
                
                r = float(action.get('r', 0))
                p = float(action.get('p', 0))
                y = float(action.get('y', 0))
                ear = float(action.get('a', 0))
                delay = max(float(action.get('d', 1.0)), 0.2)  # Minimum 0.2s delay
                
                _LOGGER.info(f"Motion Step {i+1}: R={r}, P={p}, Y={y}, Ear={ear}, Delay={delay}")

                # Calculate Motor Angles (IK)
                m1, m2, m3 = self.transformer.rpy_to_abc_rotation(r, p, y)
                
                # Send Command via HA API
                await self.send_cmd(m1, m2, m3, ear)
                
                # Delay (Async, interruptible)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                    break  # stop_event was set
                except asyncio.TimeoutError:
                    pass  # Timeout reached, continue
                    
        except Exception as e:
            _LOGGER.error(f"Sequence Error: {e}")
        finally:
            _LOGGER.info("Robot Sequence Ended")

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
            # Robust Regex: Find [ ... ] block anywhere, accommodating Markdown ```json ... ``` wrapper
            # Pattern: 
            # 1. Optional ```json (or just ```)
            # 2. [ ... ] (Non-greedy content)
            # 3. Optional ```
            
            robot_action_task = None
            json_pattern = r'(\[.*?\])'
            
            # Simple Search for array structure first
            match = re.search(json_pattern, text, re.DOTALL)
            
            if match:
                json_str = match.group(1)
                
                try:
                    # Attempt parse
                    actions = json.loads(json_str)
                    _LOGGER.info(f"Robot Actions Found: {len(actions)} steps")
                    
                    # Start Robot Task
                    robot_action_task = asyncio.create_task(robot_controller.run_sequence(actions))
                    
                    # Remove the JSON part from text for TTS
                    # Also clean up potential surrounding backticks if they exist
                    start, end = match.span(1)
                    
                    # Check for preceding ``` or ```json
                    pre_text = text[:start]
                    post_text = text[end:]
                    
                    # Simple cleanup: Remove markdown code block markers if they were wrapping the JSON
                    # If pre_text ends with ```json or ``` and post_text starts with ```
                    pre_text = re.sub(r'```\w*\s*$', '', pre_text)
                    post_text = re.sub(r'^\s*```', '', post_text)
                    
                    text = (pre_text + post_text).strip()
                    
                    if not text:
                        text = " " # Prevent empty text error
                        
                except json.JSONDecodeError:
                    _LOGGER.warning(f"Found bracket block but failed to parse JSON: {json_str[:20]}...")
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
                
                # Robot sequence runs independently - don't stop it when TTS ends
                # It will complete on its own based on its delay timings
                # robot_controller.stop() removed - let sequence complete

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
# SR Voice Assistant + Chat UI

Home Assistant용 통합 음성 어시스턴트 애드온 + 실시간 대화 기록 웹 UI

## 특징

- 🎤 **STT (Speech-to-Text)**: Google Speech Recognition으로 음성 인식
- 🔊 **TTS (Text-to-Speech)**: gTTS로 음성 합성
- 💬 **실시간 Chat UI**: 모든 대화를 카카오톡 스타일 웹 UI에서 확인
- 📝 **자동 기록**: STT/TTS 발생 시 자동으로 Chat UI에 기록
- 🔌 **Wyoming Protocol**: Home Assistant 음성 어시스턴트 완전 통합
- 📊 **이벤트 발생**: Home Assistant에서 자동화 가능
- 🌍 **다국어 지원**: 한국어, 영어, 일본어, 중국어 등

## 새로운 기능 (v3.0.0)

### 🎨 실시간 대화 웹 UI
- **카카오톡 스타일** 채팅 인터페이스
- **실시간 업데이트**: WebSocket으로 즉시 반영
- **30일 자동 정리**: 오래된 대화는 자동 삭제
- **역할 구분**:
  - 🎤 사용자 음성 (STT) → 노란색 말풍선 (오른쪽)
  - 🔊 어시스턴트 응답 (TTS) → 흰색 말풍선 (왼쪽)

### 🔄 직접 통합
기존에는 `HA 이벤트 → 자동화 → Flask POST` 과정이 필요했지만,
이제는 **STT/TTS 발생 시 바로 Chat UI로 전송**되어 별도 자동화 불필요!

## 설치 방법

1. Home Assistant → 설정 → 추가 기능
2. 우측 상단 ⋮ → Repositories
3. 저장소 URL 추가:
   ```
   https://github.com/JS-HAN-1987/sr-voice-assistant-addon
   ```
4. "SR Voice Assistant + Chat UI" 설치
5. 설정 조정
6. Start 클릭

## 설정

```yaml
language: ko                # 기본 언어
ha_ip: homeassistant        # HA IP 주소
api_token: ""               # HA Long-Lived Token (선택)
chat_ui_port: 9822          # Chat UI 포트
```

### 지원 언어

- 한국어: ko-KR / ko
- 영어(미국): en-US / en
- 일본어: ja-JP / ja
- 중국어(간체): zh-CN

## 사용 방법

### 1. Chat UI 접속

애드온 시작 후 다음 주소로 접속:

```
http://homeassistant.local:9822
```

또는 애드온 페이지에서 **"웹 UI 열기"** 버튼 클릭!

### 2. Wyoming Protocol 설정

#### STT 설정
1. 설정 → 음성 어시스턴트 → Speech-to-Text
2. "Wyoming Protocol" 선택
3. 서버: `homeassistant.local:10300`

#### TTS 설정
1. 설정 → 음성 어시스턴트 → Text-to-Speech
2. "Wyoming Protocol" 선택
3. 서버: `homeassistant.local:10400`

### 3. 음성 인식/합성 테스트

음성 어시스턴트를 사용하면:
1. 🎤 음성 인식 → 자동으로 Chat UI에 기록 (노란색, 오른쪽)
2. 🔊 음성 합성 → 자동으로 Chat UI에 기록 (흰색, 왼쪽)
3. 💬 실시간으로 화면에 표시

## Home Assistant 통합

### 발생 이벤트

- `voice_stt` - STT 완료 시 발생
  ```yaml
  event_data:
    text: "거실 불 켜줘"
    language: "ko-KR"
  ```

- `voice_tts` - TTS 완료 시 발생
  ```yaml
  event_data:
    text: "거실 불을 켰습니다"
  ```

### 자동화 예제

#### 대화 내용을 알림으로 보내기
```yaml
automation:
  - alias: "음성 대화 알림"
    trigger:
      - platform: event
        event_type: voice_stt
    action:
      - service: notify.mobile_app
        data:
          title: "🎤 음성 인식"
          message: "{{ trigger.event.data.text }}"
```

## Chat UI 기능

### 특징
- ✅ 실시간 메시지 수신 (WebSocket)
- ✅ 30일 이후 자동 삭제
- ✅ 카카오톡 스타일 UI
- ✅ 모바일 반응형 디자인
- ✅ 자동 스크롤 (최신 메시지로)

### 데이터 저장 위치
```
/data/chat_db.json
```

### 수동 대화 추가 (API)
```bash
curl -X POST http://homeassistant.local:9822/add \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "message": "테스트 메시지"}'
```

## 디렉토리 구조

```
/
├── run.sh                  # 실행 스크립트
├── wyoming_stt.py          # STT 서버 (→ Chat UI 전송)
├── wyoming_tts.py          # TTS 서버 (→ Chat UI 전송)
├── utils.py                # 유틸리티 (HA 이벤트, Chat UI POST)
├── app.py                  # Flask Chat UI 서버
├── requirements.txt        # Python 의존성
├── Dockerfile              # Docker 이미지 빌드
├── config.yaml             # 애드온 설정
├── templates/
│   └── index.html          # Chat UI HTML
└── static/
    └── style.css           # Chat UI 스타일
```

## 지원 아키텍처

- aarch64 (Raspberry Pi 4/5 64-bit)
- amd64 (Intel/AMD 64-bit)
- armv7 (Raspberry Pi 3/4 32-bit)
- armhf (ARM 32-bit)

## 문제 해결

### Chat UI가 표시되지 않을 때
1. 애드온 로그에서 "Flask Chat UI 서버 시작" 확인
2. http://homeassistant.local:9822 접속 테스트
3. 포트 9822가 다른 서비스와 충돌하지 않는지 확인

### 대화가 기록되지 않을 때
1. 애드온 로그에서 "Chat UI 전송" 메시지 확인
2. /data/chat_db.json 파일 존재 확인
3. Wyoming STT/TTS가 정상 작동하는지 확인

### 음성 인식/합성이 안 될 때
- 인터넷 연결 확인 (Google API 사용)
- 언어 설정 확인
- Wyoming 포트 설정 확인 (STT: 10300, TTS: 10400)

## 기술 스택

- **Backend**: Python, Flask, Flask-SocketIO
- **Frontend**: HTML, CSS, JavaScript, Socket.IO
- **STT**: Google Speech Recognition
- **TTS**: gTTS (Google Text-to-Speech)
- **Protocol**: Wyoming Protocol
- **Storage**: JSON 파일 기반

## 버전 히스토리

- **3.0.0**: 
  - ✨ 실시간 Chat UI 추가
  - ✨ STT/TTS → Chat UI 직접 전송 (자동화 불필요)
  - ✨ 30일 자동 정리 기능
  - ✨ 카카오톡 스타일 UI
- **2.0.1**: Wyoming Protocol 안정화
- **1.0.0**: 초기 릴리스 (STT + TTS)

## 라이센스

MIT License

## 유지보수자

JS-HAN-1987

## 피드백 및 기여

이슈 및 PR은 GitHub 저장소에서 환영합니다!
https://github.com/JS-HAN-1987/sr-voice-assistant-addon
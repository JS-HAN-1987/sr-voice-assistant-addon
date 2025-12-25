# SR Voice Assistant Add-on

Home Assistant용 통합 음성 어시스턴트 애드온입니다.

## 특징

- 🎤 **STT (Speech-to-Text)**: Google Speech Recognition으로 음성 인식
- 🔊 **TTS (Text-to-Speech)**: gTTS로 음성 합성
- 📝 **HA 센서 통합**: 최근 대화를 센서로 표시
- 📊 **이벤트 발생**: Home Assistant에서 자동화 및 히스토리 관리 가능
- 🔌 **Wyoming Protocol**: Home Assistant 음성 어시스턴트 완전 통합
- 🌍 **다국어 지원**: 한국어, 영어, 일본어, 중국어 등

## 설치 방법

1. Home Assistant → 설정 → 추가 기능
2. 우측 상단 ⋮ → Repositories
3. 저장소 URL 추가:
   ```
   https://github.com/JS-HAN-1987/sr-voice-assistant-addon
   ```
4. "SR Voice Assistant" 설치
5. 설정 조정
6. Start 클릭

## 설정

```yaml
api_port: 5007              # REST API 포트
stt_wyoming_port: 10300     # STT Wyoming 포트
tts_wyoming_port: 10400     # TTS Wyoming 포트
language: ko-KR             # 기본 언어
```

### 지원 언어

- 한국어: ko-KR / ko
- 영어(미국): en-US / en
- 일본어: ja-JP / ja
- 중국어(간체): zh-CN

## Home Assistant 대시보드 설정

### 1. 자동 생성 센서

애드온이 자동으로 생성하는 센서:

- `sensor.voice_last_stt` - 마지막 STT(음성→텍스트) 결과
- `sensor.voice_last_tts` - 마지막 TTS(텍스트→음성) 텍스트

### 2. 발생 이벤트

- `voice_stt` - STT 완료 시 발생
  ```yaml
  event_data:
    text: "거실 불 켜줘"
    timestamp: "2024-12-25T10:30:00"
    language: "ko-KR"
  ```

- `voice_tts` - TTS 완료 시 발생
  ```yaml
  event_data:
    text: "거실 불을 켰습니다"
    timestamp: "2024-12-25T10:30:01"
    language: "ko"
  ```

### 3. 대시보드 카드 - 최근 대화

#### 기본 카드
```yaml
type: entities
title: 🎤 음성 대화
entities:
  - entity: sensor.voice_last_stt
    name: 마지막 음성 인식
    icon: mdi:microphone
  - entity: sensor.voice_last_tts
    name: 마지막 음성 출력
    icon: mdi:speaker
```

#### Markdown 카드
```yaml
type: markdown
title: 🗣️ 최근 대화
content: |
  **🎤 음성 인식:**
  {{ states('sensor.voice_last_stt') }}
  _{{ state_attr('sensor.voice_last_stt', 'timestamp') }}_
  
  **🔊 음성 출력:**
  {{ states('sensor.voice_last_tts') }}
  _{{ state_attr('sensor.voice_last_tts', 'timestamp') }}_
```

### 4. 대화 히스토리 보기 (Home Assistant 기본 기능 사용)

#### Logbook 카드로 전체 대화 기록 확인
```yaml
type: logbook
title: 📝 음성 대화 기록
entities:
  - sensor.voice_last_stt
  - sensor.voice_last_tts
hours_to_show: 24
```

#### History 그래프로 시간별 보기
```yaml
type: history-graph
title: 📊 대화 히스토리
entities:
  - entity: sensor.voice_last_stt
  - entity: sensor.voice_last_tts
hours_to_show: 24
```

#### Logbook 페이지에서 전체 보기
- 좌측 메뉴 → **Logbook**
- 필터에서 `sensor.voice_last_stt`, `sensor.voice_last_tts` 선택
- 모든 대화 내역이 시간순으로 표시됨

#### History 페이지에서 전체 보기
- 좌측 메뉴 → **History**
- `sensor.voice_last_stt`, `sensor.voice_last_tts` 선택
- 시간별 그래프와 상세 내역 확인

### 5. 자동화 예제

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

#### Logbook에 커스텀 메시지로 기록
```yaml
automation:
  - alias: "음성 대화 로깅"
    trigger:
      - platform: event
        event_type: voice_stt
      - platform: event
        event_type: voice_tts
    action:
      - service: logbook.log
        data:
          name: "음성 어시스턴트"
          message: |
            {% if trigger.event.event_type == 'voice_stt' %}
            🎤 {{ trigger.event.data.text }}
            {% else %}
            🔊 {{ trigger.event.data.text }}
            {% endif %}
          entity_id: automation.voice_conversation_logger
```

#### 특정 키워드 감지
```yaml
automation:
  - alias: "긴급 키워드 감지"
    trigger:
      - platform: event
        event_type: voice_stt
    condition:
      - condition: template
        value_template: >
          {{ '도와줘' in trigger.event.data.text or 
             '긴급' in trigger.event.data.text }}
    action:
      - service: notify.notify
        data:
          title: "⚠️ 긴급 음성 감지"
          message: "{{ trigger.event.data.text }}"
```

#### 대화 내용을 파일에 저장 (CSV, JSON 등)
```yaml
automation:
  - alias: "대화 파일 저장"
    trigger:
      - platform: event
        event_type: voice_stt
      - platform: event
        event_type: voice_tts
    action:
      - service: notify.persistent_notification
        data:
          title: "대화 기록됨"
          message: |
            타입: {{ trigger.event.event_type }}
            내용: {{ trigger.event.data.text }}
            시간: {{ trigger.event.data.timestamp }}
```

#### 대화 카운터 (Helper 사용)
```yaml
# configuration.yaml에 counter 추가
counter:
  voice_conversations:
    name: 총 대화 횟수
    icon: mdi:message-text
    step: 1

# 자동화
automation:
  - alias: "대화 카운터 증가"
    trigger:
      - platform: event
        event_type: voice_stt
    action:
      - service: counter.increment
        target:
          entity_id: counter.voice_conversations
```

### 6. 고급 대시보드 구성

#### 통합 대화 뷰
```yaml
type: vertical-stack
title: 🎙️ 음성 어시스턴트
cards:
  - type: entities
    entities:
      - entity: sensor.voice_last_stt
        name: 🎤 마지막 음성 인식
      - entity: sensor.voice_last_tts
        name: 🔊 마지막 음성 출력
      - entity: counter.voice_conversations
        name: 📊 총 대화 횟수
  
  - type: logbook
    entities:
      - sensor.voice_last_stt
      - sensor.voice_last_tts
    hours_to_show: 12
```

## REST API 사용법

### STT - 음성을 텍스트로
```bash
curl -X POST http://homeassistant.local:5007/stt \
  -F "file=@audio.wav"
```

**응답:**
```json
{
  "result": "안녕하세요",
  "timestamp": "2024-12-25T10:30:00"
}
```

### TTS - 텍스트를 음성으로
```bash
curl -X POST http://homeassistant.local:5007/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "안녕하세요"}' \
  --output speech.mp3
```

## Wyoming Protocol 통합

### STT 설정
1. 설정 → 음성 어시스턴트 → Speech-to-Text
2. "Wyoming Protocol" 선택
3. 서버: `homeassistant.local:10300`

### TTS 설정
1. 설정 → 음성 어시스턴트 → Text-to-Speech
2. "Wyoming Protocol" 선택
3. 서버: `homeassistant.local:10400`

## 지원 아키텍처

- aarch64 (Raspberry Pi 4/5 64-bit)
- amd64 (Intel/AMD 64-bit)
- armv7 (Raspberry Pi 3/4 32-bit)
- armhf (ARM 32-bit)

## 문제 해결

### 센서가 생성되지 않을 때
1. 애드온 로그에서 "센서 업데이트 성공" 메시지 확인
2. Home Assistant 재시작
3. 개발자 도구 → 상태에서 `sensor.voice_last_*` 검색

### 이벤트가 발생하지 않을 때
1. 개발자 도구 → 이벤트에서 수신 대기
2. `voice_stt` 또는 `voice_tts` 입력 후 "이벤트 수신 시작"
3. 음성 인식/출력 테스트
4. 애드온 로그 확인

### 음성 인식/합성이 안 될 때
- 인터넷 연결 확인 (Google API 사용)
- 언어 설정 확인
- 오디오 파일 형식 확인 (STT는 WAV 권장)

## 대화 기록 관리 팁

Home Assistant는 기본적으로 모든 센서 변화를 데이터베이스에 기록합니다:

- **Logbook**: 모든 이벤트와 상태 변화를 시간순으로 표시
- **History**: 센서 값의 변화를 그래프로 표시
- **Recorder**: 기본 10일간 데이터 보관 (설정 가능)

### 기록 보존 기간 설정
```yaml
# configuration.yaml
recorder:
  purge_keep_days: 30  # 30일간 보관
  include:
    entities:
      - sensor.voice_last_stt
      - sensor.voice_last_tts
```

### 무한 보관 (주의: DB 크기 증가)
```yaml
recorder:
  purge_keep_days: 365
  commit_interval: 1
```

## 라이센스

MIT License

## 유지보수자

JS-HAN-1987

## 버전 히스토리

- **1.0.0**: 초기 릴리스 (STT + TTS + HA 이벤트/센서 통합)
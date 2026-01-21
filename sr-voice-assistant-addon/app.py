import json
import os
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, jsonify, send_from_directory
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

DB_FILE = '/data/chat_db.json'

# HTML 템플릿 (인라인)
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>음성 대화 기록</title>
    <style>
body {
    margin: 0;
    font-family: "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
    background-color: #e5e5e5;
}

.chat-container {
    height: 100vh;
    padding: 15px;
    overflow-y: auto;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
}

.chat-row:first-child {
    margin-top: auto !important;
}

.chat-row {
    display: flex;
    margin-bottom: 10px;
}

.chat-row.user {
    justify-content: flex-end;
}

.chat-row.user .bubble {
    background-color: #fef01b;
    border-radius: 15px 15px 0 15px;
}

.chat-row.assistant {
    justify-content: flex-start;
}

.chat-row.assistant .bubble {
    background-color: white;
    border-radius: 15px 15px 15px 0;
}

.bubble {
    max-width: 70%;
    padding: 10px 14px;
    font-size: 15px;
    line-height: 1.4;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    word-break: break-word;
}
    </style>
</head>
<body>
<div class="chat-container" id="chat">
    {% for chat in chat_history %}
        <div class="chat-row {{ chat.role }}">
            <div class="bubble">
                {{ chat.message }}
            </div>
        </div>
    {% endfor %}
</div>

<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<script>
    const chat = document.getElementById("chat");
    
    window.onload = function() {
        chat.scrollTop = chat.scrollHeight;
    };

    const socket = io(); 
    socket.on("new_message", data => {
        const row = document.createElement("div");
        row.className = `chat-row ${data.role}`;

        const bubble = document.createElement("div");
        bubble.className = "bubble";
        bubble.innerText = data.message;

        row.appendChild(bubble);
        chat.appendChild(row);

        chat.scrollTop = chat.scrollHeight;
    });
</script>
</body>
</html>"""

def load_and_clean_history():
    """파일에서 대화를 불러오고 30일이 지난 데이터는 삭제"""
    if not os.path.exists(DB_FILE):
        return []
    
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        one_month_ago = datetime.now() - timedelta(days=30)
        
        clean_history = [
            msg for msg in history 
            if "timestamp" not in msg or datetime.fromisoformat(msg["timestamp"]) > one_month_ago
        ]
        return clean_history
    except Exception as e:
        print(f"[ERROR] 히스토리 로드 실패: {e}")
        return []

chat_history = load_and_clean_history()

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, chat_history=chat_history)

@app.route("/add", methods=["POST"])
def add_message():
    global chat_history
    data = request.json
    
    new_msg = {
        "role": data["role"],
        "message": data["message"],
        "timestamp": datetime.now().isoformat()
    }
    
    # --- Robot Control JSON Filter ---
    try:
        if new_msg["role"] == "assistant":
            # Remove [ ... ] JSON block if present
            import re
            json_pattern = r'(\[.*?\])'
            new_msg["message"] = re.sub(json_pattern, '', new_msg["message"], flags=re.DOTALL).strip()
            # Also clean up potential markdown block artifacts around it
            new_msg["message"] = re.sub(r'^```json\s*', '', new_msg["message"])
            new_msg["message"] = re.sub(r'^```\s*', '', new_msg["message"])
            new_msg["message"] = re.sub(r'```\s*$', '', new_msg["message"]).strip()
    except:
        pass
    # ---------------------------------
    
    chat_history.append(new_msg)
    
    # 30일 지난 데이터 정리
    chat_history = [
        msg for msg in chat_history 
        if datetime.fromisoformat(msg["timestamp"]) > (datetime.now() - timedelta(days=30))
    ]
    
    # 파일 저장
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[ERROR] 파일 저장 실패: {e}")
    
    # WebSocket으로 실시간 전송
    socketio.emit("new_message", new_msg)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    print("[INFO] Flask Chat UI 서버 시작 (Port 9822)...")
    socketio.run(app, host="0.0.0.0", port=9822)
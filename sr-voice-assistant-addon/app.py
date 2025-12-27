import json
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

DB_FILE = '/data/chat_db.json'

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
    return render_template("index.html", chat_history=chat_history)

@app.route("/add", methods=["POST"])
def add_message():
    global chat_history
    data = request.json
    
    new_msg = {
        "role": data["role"],
        "message": data["message"],
        "timestamp": datetime.now().isoformat()
    }
    
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
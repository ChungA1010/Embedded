"""
라즈베리파이: Mobius의 cmd 컨테이너 구독 -> 모니터 문구 표시 + 감정 폴더 음악 재생 (수정판 v3)

v2에서 고친 것:
  1) sur 필터 추가 - cmd 구독에서 온 알림만 처리 (온습도/좌석 알림 오작동 방지)
  2) tkinter 스레드 안전성 - queue로 UI 갱신 (MQTT 스레드에서 직접 UI 호출 금지)
  3) 음악 경로를 홈 디렉토리 기준으로 자동 설정 (사용자 이름이 pi가 아니어도 동작)
  4) mpg123 없을 때/폴더 없을 때 명확한 안내 출력

설치 (라즈베리파이에서 한 번만):
    sudo apt update
    sudo apt install -y mpg123 fonts-nanum python3-tk
    pip install "paho-mqtt>=2.0" --break-system-packages
"""
import json
import os
import queue
import random
import subprocess
import threading
import tkinter as tk
import paho.mqtt.client as mqtt

# ---- 설정값 ----
MQTT_HOST = "onem2m.iotcoss.ac.kr"
MQTT_PORT = 11883
ORIGIN = "SOrigin_jjjn"
SUB_TOPIC = f"/oneM2M/req/Mobius/{ORIGIN}/#"
COMMAND_MARKER = "cmd"          # sur 안에 이 단어가 있는 알림만 처리
MUSIC_DIR = os.path.expanduser("~/bgm")   # 홈디렉토리/music (사용자 이름 무관)

ui_queue = queue.Queue()            # MQTT 스레드 -> 화면 스레드로 문구 전달


# =========================================================
# 1) 모니터 화면
# =========================================================
class ScreenDisplay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="black")
        self.label = tk.Label(
            self.root, text=" ", font=("NanumGothic", 48),
            fg="white", bg="black", wraplength=1000, justify="center"
        )
        self.label.pack(expand=True)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.poll_queue()   # 큐 폴링 시작

    def poll_queue(self):
        """100ms마다 큐를 확인해서 새 문구가 있으면 화면 갱신 (메인 스레드에서만 UI 조작)"""
        try:
            while True:
                text = ui_queue.get_nowait()
                self.label.config(text=text)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def run(self):
        self.root.mainloop()


# =========================================================
# 2) 스피커 (감정 폴더에서 랜덤 재생)
# =========================================================
def play_music(mood: str):
    folder = os.path.join(MUSIC_DIR, mood)
    if not os.path.isdir(folder):
        print(f"[스피커] 폴더 없음: {folder} - 건너뜀")
        return
    files = [f for f in os.listdir(folder) if f.lower().endswith((".mp3", ".wav"))]
    if not files:
        print(f"[스피커] {folder} 안에 음악 파일 없음")
        return
    path = os.path.join(folder, random.choice(files))

    #subprocess.run(["pkill", "-f", "mpg123"], stderr=subprocess.DEVNULL)
    try:
        subprocess.Popen(["paplay", path])    
        print(f"[스피커] {mood} -> {os.path.basename(path)} 재생")
    except FileNotFoundError:
        print("[스피커] mpg123이 설치 안 됨: sudo apt install mpg123")


# =========================================================
# 3) command 처리
# =========================================================
def handle_command(payload: dict):
    lcd_text = payload.get("lcd", "")
    mood = payload.get("detected_mood", "calm")
    print(f"[명령 수신] mood={mood}, lcd={lcd_text}")

    play_music(mood)
    if lcd_text:
        ui_queue.put(lcd_text)      # 직접 UI 호출 대신 큐에 넣기


# =========================================================
# 4) MQTT
# =========================================================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("MQTT 연결 성공, 구독:", SUB_TOPIC)
        client.subscribe(SUB_TOPIC)
    else:
        print("MQTT 연결 실패, rc =", rc)


def on_message(client, userdata, msg):
    print(msg.payload.decode('utf-8'))
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        sgn = data.get("pc",{}).get("m2m:sgn", {})

        # --- 필터: command 구독에서 온 알림만 처리 ---
        sur = sgn.get("sur", "")
        if COMMAND_MARKER not in sur:
            return   # 온습도/좌석 등 다른 컨테이너 알림은 무시

        cin = sgn.get("nev", {}).get("rep", {}).get("m2m:cin", {})
        con_raw = cin.get("con")
        if con_raw is None:
            return   # 구독 생성 확인용(verification) 알림 등은 무시
        payload = json.loads(con_raw) if isinstance(con_raw, str) else con_raw
        handle_command(payload)
    except Exception as e:
        print("[메시지 처리 오류]", e, "| 원본:", msg.payload[:200])


def mqtt_thread():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    threading.Thread(target=mqtt_thread, daemon=True).start()
    print("대기 중... command에 새 명령이 오면 화면/스피커로 반영")
    ScreenDisplay().run()

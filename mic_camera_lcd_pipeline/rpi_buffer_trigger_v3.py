"""
RPi4 쪽 버퍼링 + 트리거 전송 모듈 v3 (오디오는 텍스트 대신 원본 그대로 전송)

v3 변경점:
- 마이크: transcript(텍스트) 대신 audio_base64(WAV 원본)를 전송. STT는 Colab 서버에서 처리.
- 카메라: v2와 동일 (seat_id별 최신 1장)
"""

import glob
import json
import os
import time
import requests

# ============================================================
# 설정
# ============================================================

MIC_DIR = "여기에_마이크_jsonl_폴더_경로"
CAMERA_DIR = "여기에_카메라_캡처_폴더_경로(하위 폴더까지 재귀 탐색됨)"

NGROK_URL = "https://xxxx-xx-xx-xxx-xx.ngrok-free.app"
DECIDE_ENDPOINT = f"{NGROK_URL}/decide"

SEAT_IDS = ["seat_1", "seat_2"]

WINDOW_SEC = 60           # 이 시간(초) 안의 마이크 녹음만 사용
CAMERA_MAX_AGE_SEC = 60   # 이 시간(초)보다 오래된 카메라 캡처는 안 씀


# ============================================================
# 1) 마이크: 가장 최근 녹음 1건만 사용 (트리거당 1회 녹음이 기본 전제)
# ============================================================

def read_latest_mic(since_ts_ms: float):
    """MIC_DIR 안의 모든 .jsonl 파일을 훑어서, since_ts_ms 이후의 가장 최근 녹음 1건 반환."""
    latest = None
    for path in glob.glob(os.path.join(MIC_DIR, "*.jsonl")):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("ts", 0) < since_ts_ms:
                    continue
                if latest is None or entry.get("ts", 0) > latest.get("ts", 0):
                    latest = entry
    return latest


# ============================================================
# 2) 카메라: 좌석별로 최신 캡처 1장씩 추출 (v2와 동일)
# ============================================================

def read_latest_camera_by_seat(now_ms: float) -> dict:
    latest_by_seat = {}
    for path in glob.glob(os.path.join(CAMERA_DIR, "**", "*.json"), recursive=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        seat_id = entry.get("seat_id")
        if seat_id not in SEAT_IDS:
            continue
        cur = latest_by_seat.get(seat_id)
        if cur is None or entry.get("ts", 0) > cur.get("ts", 0):
            latest_by_seat[seat_id] = entry

    fresh = {}
    for seat_id, entry in latest_by_seat.items():
        if now_ms - entry.get("ts", 0) <= CAMERA_MAX_AGE_SEC * 1000:
            fresh[seat_id] = entry
    return fresh


# ============================================================
# 3) 트리거 시 payload 조립 + 전송
# ============================================================

def build_payload() -> dict:
    now_ms = time.time() * 1000
    since_ts_ms = now_ms - WINDOW_SEC * 1000

    mic_entry = read_latest_mic(since_ts_ms)
    camera_by_seat = read_latest_camera_by_seat(now_ms)

    payload = {}

    if mic_entry is not None:
        payload["audio_base64"] = mic_entry["audio_base64"]
        payload["loudness_db"] = mic_entry.get("loudness_db")

    if camera_by_seat:
        payload["images"] = [
            {"seat_id": seat_id, "image_base64": entry["image_base64"]}
            for seat_id, entry in sorted(camera_by_seat.items())
        ]

    payload["seated_count"] = len(camera_by_seat) if camera_by_seat else None

    return payload


def trigger_decision() -> dict:
    payload = build_payload()

    printable = {k: v for k, v in payload.items() if k not in ("images", "audio_base64")}
    print("전송할 payload:")
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    if "images" in payload:
        for img in payload["images"]:
            print(f"  - {img['seat_id']}: image_base64 ({len(img['image_base64'])}자, 생략)")
    if "audio_base64" in payload:
        print(f"  - audio_base64 ({len(payload['audio_base64'])}자, 생략)")

    try:
        res = requests.post(DECIDE_ENDPOINT, json=payload, timeout=120)
        result = res.json()
    except Exception as e:
        print(f"[trigger_decision] 전송 실패: {e}")
        return {"action": "no_action"}

    print("응답:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ============================================================
# 4) 좌석 센서 자리
# ============================================================

def on_seated_triggered() -> dict:
    return trigger_decision()


# ============================================================
# 5) 수동 테스트용 진입점
# ============================================================

if __name__ == "__main__":
    input("트리거를 발생시키려면 Enter를 누르세요...")
    trigger_decision()

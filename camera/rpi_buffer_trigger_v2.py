"""
RPi4 쪽 버퍼링 + 트리거 전송 모듈 v2.0 (단일 공용 공간 모델)

전제:
- scenario / room_id 없음 (공간이 하나뿐이므로 구분 불필요)
- 마이크: MIC_DIR에 jsonl로 계속 append (좌석 구분 없이 테이블 전체 대화)
- 카메라: CAMERA_DIR 아래(하위 폴더 포함)에 좌석별로 캡처 파일이 쌓임
  (seat_id로 구분, 트리거당 여러 장 버스트로 찍히더라도 판단 시엔 좌석당 최신 1장만 사용)

트리거가 발생하면:
1. MIC_DIR의 jsonl 전부 훑어서 최근 WINDOW_SEC 안의 발화만 추출
2. CAMERA_DIR(하위 폴더 포함) 전부 훑어서 seat_1/seat_2 각각의 최신(且 너무 오래되지 않은) 캡처 추출
3. 합쳐서 decide() 스키마의 payload로 변환 후 LLM 서버로 전송

나중에 좌석 센서 인터럽트에서 on_seated_triggered()만 호출하면 그대로 전환됩니다.
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

SEAT_IDS = ["seat_1", "seat_2"]  # 좌석 늘어나면 여기만 추가

WINDOW_SEC = 60           # 트리거 시점 기준, 이 시간(초) 안의 마이크 발화만 모음 (쿨다운과 동일)
CAMERA_MAX_AGE_SEC = 60   # 이 시간(초)보다 오래된 카메라 캡처는 안 씀


# ============================================================
# 1) 마이크: 폴더 안 jsonl 파일들을 스캔해서 시간 윈도우 안의 데이터만 추출
# ============================================================

def read_mic_window(since_ts_ms: float) -> list:
    """MIC_DIR 안의 모든 .jsonl 파일을 훑어서 since_ts_ms 이후 발화만 반환 (좌석 구분 없음)."""
    entries = []
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
                entries.append(entry)
    entries.sort(key=lambda e: e.get("ts", 0))
    return entries


# ============================================================
# 2) 카메라: 좌석별로 최신 캡처 1장씩 추출 (하위 폴더까지 재귀 탐색)
# ============================================================

def read_latest_camera_by_seat(now_ms: float) -> dict:
    """CAMERA_DIR(하위 폴더 포함) 전부 훑어서, seat_id별 최신(且 너무 안 오래된) 캡처 반환."""
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

    mic_entries = read_mic_window(since_ts_ms)
    camera_by_seat = read_latest_camera_by_seat(now_ms)

    combined_transcript = " ".join(e["transcript"] for e in mic_entries) if mic_entries else ""

    payload = {
        "transcript": combined_transcript,
    }

    if mic_entries:
        avg_loudness = sum(e["loudness_db"] for e in mic_entries) / len(mic_entries)
        payload["loudness_db_avg"] = round(avg_loudness, 1)

    if camera_by_seat:
        payload["images"] = [
            {"seat_id": seat_id, "image_base64": entry["image_base64"]}
            for seat_id, entry in sorted(camera_by_seat.items())
        ]

    payload["seated_count"] = len(camera_by_seat) if camera_by_seat else None

    return payload


def trigger_decision() -> dict:
    """트리거 발생 시 호출. 지금은 수동 호출, 나중엔 좌석 센서 콜백에서 그대로 호출."""
    payload = build_payload()

    printable = {k: v for k, v in payload.items() if k != "images"}
    print("전송할 payload:")
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    if "images" in payload:
        for img in payload["images"]:
            print(f"  - {img['seat_id']}: image_base64 ({len(img['image_base64'])}자, 생략)")

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
# 4) 좌석 센서 자리 (지금은 스텁, 나중에 인터럽트 콜백으로 교체)
# ============================================================

def on_seated_triggered() -> dict:
    """
    나중에 좌석 센서(seated_count>=2 감지) 인터럽트에서 이 함수를 그대로 호출하면 됩니다.
    """
    return trigger_decision()


# ============================================================
# 5) 수동 테스트용 진입점
# ============================================================

if __name__ == "__main__":
    input("트리거를 발생시키려면 Enter를 누르세요...")
    trigger_decision()

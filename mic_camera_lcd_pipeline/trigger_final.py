"""
0) oneM2M에서 seatA, seatB를 polling
1) 둘 다 occupied=True가 되면 트리거 통과
2) 카메라 seat_1 -> 카메라 seat_2 -> 마이크 녹음 -> 서버 전송
"""

import base64
import json
import os
import time

import requests

import record_wav_only
from send_wav_to_server import _calc_loudness_db
from capture_v2 import CameraCapture
import rpi_buffer_trigger_v3 as rbt

from secrets import ONEM2M_ORIGIN, API_KEY, LECTURE, CREATOR

# ============================================================
# 테스트 설정
# ============================================================

NGROK_URL = "https://ancient-attentive-cursive.ngrok-free.dev"
DECIDE_ENDPOINT = f"{NGROK_URL}/decide"

rbt.CAMERA_DIR = "./captures"

TEST_CAPTURE_COUNT = 3
TEST_CAPTURE_INTERVAL_SEC = 1
STEP_GAP_SEC = 0.5

# ============================================================
# oneM2M 설정
# ============================================================

ONEM2M_HOST = "https://onem2m.iotcoss.ac.kr"
CSEBASE = "/Mobius"
AE_RN = "ae_table"

SEAT_A_URL = f"{ONEM2M_HOST}{CSEBASE}/{AE_RN}/seatA/la"
SEAT_B_URL = f"{ONEM2M_HOST}{CSEBASE}/{AE_RN}/seatB/la"

ONEM2M_HEADERS = {
    "X-M2M-Origin": ONEM2M_ORIGIN,   # 실제 값으로 변경
    "X-M2M-RI": "ri-seat-check",
    "X-M2M-RVI": "2a",
    "X-API-KEY": API_KEY,                # 실제 값으로 변경
    "X-AUTH-CUSTOM-LECTURE": LECTURE,    # 실제 값으로 변경
    "X-AUTH-CUSTOM-CREATOR": CREATOR,    # 실제 값으로 변경
    "Accept": "application/json"
}

POLL_INTERVAL_SEC = 2


def get_latest_seat_state(url, seat_name):
    """
    oneM2M latest CIN에서 seat 상태 1회 조회
    반환값 예:
    {
        "occupied": True,
        "distance": 24
    }
    실패 시 None 반환
    """
    try:
        res = requests.get(url, headers=ONEM2M_HEADERS, timeout=5)
        res.raise_for_status()

        data = res.json()
        con = data["m2m:cin"]["con"]

        # con이 문자열 JSON이면 다시 파싱
        if isinstance(con, str):
            con = json.loads(con)

        occupied = bool(con.get("occupied", False))
        distance = con.get("distance", -1)

        print(f"[{seat_name}] occupied={occupied}, distance={distance}")
        return {
            "occupied": occupied,
            "distance": distance,
        }

    except Exception as e:
        print(f"[오류] {seat_name} 상태 조회 실패: {e}")
        return None


def wait_until_both_seated(poll_interval=2):
    """
    seatA, seatB를 주기적으로 조회해서
    둘 다 occupied=True가 될 때까지 대기
    """
    print("\n" + "=" * 60)
    print("0) oneM2M seatA / seatB 상태 폴링 시작")
    print("=" * 60)

    while True:
        seat_a = get_latest_seat_state(SEAT_A_URL, "seatA")
        seat_b = get_latest_seat_state(SEAT_B_URL, "seatB")

        if seat_a is not None and seat_b is not None:
            if seat_a["occupied"] and seat_b["occupied"]:
                print("[트리거 통과] seatA, seatB 모두 착석 상태입니다. 캡처를 시작합니다.")
                return

            print("[대기] 아직 두 좌석이 모두 occupied=True가 아닙니다.")
        else:
            print("[대기] seat 상태 조회 실패. 다음 폴링에서 다시 시도합니다.")

        print(f"[대기] {poll_interval}초 후 다시 확인...\n")
        time.sleep(poll_interval)


def _capture_seat(camera, seat_id, count, interval_sec, results):
    if seat_id not in camera.cameras:
        print(f"[건너뜀] {seat_id} 카메라가 열려있지 않음")
        results[seat_id] = None
        return
    out_dir = camera.capture_series(seat_id, count=count, interval_sec=interval_sec)
    results[seat_id] = out_dir


def main():
    # --------------------------------------------------------
    # 0) seatA, seatB 둘 다 착석할 때까지 대기
    # --------------------------------------------------------
    wait_until_both_seated(POLL_INTERVAL_SEC)

    # --------------------------------------------------------
    # 1) 카메라 초기화
    # --------------------------------------------------------
    print("=" * 60)
    print("1) 카메라 초기화")
    print("=" * 60)
    camera = CameraCapture()

    if not camera.cameras:
        print("[중단] 열린 카메라가 하나도 없습니다. 연결/인덱스를 확인하세요.")
        return

    results = {}

    # --------------------------------------------------------
    # 2) 카메라 seat_1
    # --------------------------------------------------------
    print("\n" + "=" * 60)
    print("2) 카메라 seat_1 캡처")
    print("=" * 60)
    _capture_seat(camera, "seat_1", TEST_CAPTURE_COUNT, TEST_CAPTURE_INTERVAL_SEC, results)

    print(f"\n[대기] {STEP_GAP_SEC}초 대기...")
    time.sleep(STEP_GAP_SEC)

    # --------------------------------------------------------
    # 3) 카메라 seat_2
    # --------------------------------------------------------
    print("\n" + "=" * 60)
    print("3) 카메라 seat_2 캡처")
    print("=" * 60)
    _capture_seat(camera, "seat_2", TEST_CAPTURE_COUNT, TEST_CAPTURE_INTERVAL_SEC, results)

    camera.release()

    print(f"\n[대기] {STEP_GAP_SEC}초 대기...")
    time.sleep(STEP_GAP_SEC)

    # --------------------------------------------------------
    # 4) 마이크
    # --------------------------------------------------------
    print("\n" + "=" * 60)
    print("4) 마이크 녹음 (record_wav_only.record())")
    print("=" * 60)
    try:
        record_wav_only.record()
        print("[OK] 마이크 저장 완료 -> 다음 단계로 진행")
    except Exception as e:
        print(f"[WARNING] 마이크 녹음 실패, 카메라만으로 계속 진행: {e}")

    # --------------------------------------------------------
    # 5) 저장 결과 확인
    # --------------------------------------------------------
    print("\n" + "=" * 60)
    print("5) 저장 결과 확인")
    print("=" * 60)
    wav_exists = os.path.exists(record_wav_only.OUTPUT_PATH)
    print(f"mic: {record_wav_only.OUTPUT_PATH} ({'있음' if wav_exists else '없음'})")
    print(f"seat_1: {results.get('seat_1') or '실패/스킵'}")
    print(f"seat_2: {results.get('seat_2') or '실패/스킵'}")

    # --------------------------------------------------------
    # 6) payload 조립
    # --------------------------------------------------------
    print("\n" + "=" * 60)
    print("6) payload 조립")
    print("=" * 60)

    payload = {}

    if wav_exists:
        with open(record_wav_only.OUTPUT_PATH, "rb") as f:
            wav_bytes = f.read()
        payload["audio_base64"] = base64.b64encode(wav_bytes).decode("utf-8")
        payload["loudness_db"] = _calc_loudness_db(record_wav_only.OUTPUT_PATH)

    now_ms = time.time() * 1000
    camera_by_seat = rbt.read_latest_camera_by_seat(now_ms)
    if camera_by_seat:
        payload["images"] = [
            {"seat_id": seat_id, "image_base64": entry["image_base64"]}
            for seat_id, entry in sorted(camera_by_seat.items())
        ]
    payload["seated_count"] = len(camera_by_seat) if camera_by_seat else None

    printable = {k: v for k, v in payload.items() if k not in ("images", "audio_base64")}
    print(f"전송할 payload: {json.dumps(printable, ensure_ascii=False)}")
    if "audio_base64" in payload:
        print(f"  - audio_base64 ({len(payload['audio_base64'])}자, 생략)")
    if "images" in payload:
        for img in payload["images"]:
            print(f"  - {img['seat_id']}: image_base64 ({len(img['image_base64'])}자, 생략)")

    # --------------------------------------------------------
    # 7) 서버 전송
    # --------------------------------------------------------
    print("\n" + "=" * 60)
    print("7) 서버로 전송")
    print("=" * 60)
    try:
        res = requests.post(DECIDE_ENDPOINT, json=payload, timeout=120)
        result = res.json()
    except Exception as e:
        print(f"[전송 실패] {e}")
        result = {"action": "no_action"}

    print("\n" + "=" * 60)
    print("8) 최종 결과")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()

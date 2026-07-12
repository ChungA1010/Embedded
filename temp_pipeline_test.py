"""
임시 통합 테스트 스크립트 (초음파 센서 대신 손으로 트리거)
카메라(seat_1, seat_2) + 마이크(STT 포함)를 병렬로 동시 실행 -> 전부 끝나면 한 번에 서버 전송

목적:
1) 카메라/마이크 입력이 잘 들어오고, 캡처된 게 파일로 잘 저장되는지 확인
2) 저장된 파일들을 rpi_buffer_trigger가 잘 읽어서 서버로 전달하는지 확인
3) 서버(Colab)가 판단해서 응답을 잘 돌려주는지 확인

필요한 폴더 구조 (같은 폴더에):
  temp_pipeline_test.py
  capture_v2.py
  rpi_buffer_trigger_v2.py
  mic/
    __init__.py
    capture.py
    stt.py

테스트 속도를 위해 카메라는 실제 운영값(60장, 3초 간격)보다 훨씬 줄여서 캡처합니다.
운영 전환 시 capture_series(count=60, interval_sec=3)로 되돌리면 됩니다.
"""

import os
import threading
from capture_v2 import CameraCapture
from mic.capture import capture_and_save as mic_capture_and_save
import rpi_buffer_trigger_v2 as rbt

# ============================================================
# 테스트 설정 -- NGROK_URL만 실제 서버 값으로 채우면 됩니다
# ============================================================

rbt.NGROK_URL = "https://xxxx-xx-xx-xxx-xx.ngrok-free.app"
rbt.DECIDE_ENDPOINT = f"{rbt.NGROK_URL}/decide"

rbt.CAMERA_DIR = "./captures"      # capture_v2.py의 기본 저장 위치와 동일
rbt.MIC_DIR = "./mic_logs"         # mic/capture.py의 save_mic_entry()가 여기에 씀

# 테스트용 축소 캡처 설정 (운영 시 60/3으로 되돌릴 것)
TEST_CAPTURE_COUNT = 3
TEST_CAPTURE_INTERVAL_SEC = 1


# ============================================================
# 스레드에서 실행할 작업들 (결과는 공유 dict에 기록)
# ============================================================

def _run_camera_capture(camera, seat_id, count, interval_sec, results):
    if seat_id not in camera.cameras:
        print(f"[건너뜀] {seat_id} 카메라가 열려있지 않음")
        results[seat_id] = None
        return
    out_dir = camera.capture_series(seat_id, count=count, interval_sec=interval_sec)
    results[seat_id] = out_dir


def _run_mic_capture(mic_dir, results):
    try:
        entry = mic_capture_and_save(mic_dir)  # 5초 녹음 + (필요시) STT까지 여기서 다 끝남
        results["mic"] = entry
    except Exception as e:
        print(f"[WARNING] 마이크 캡처 실패: {e}")
        results["mic"] = None


def main():
    print("=" * 60)
    print("1) 카메라 초기화")
    print("=" * 60)
    camera = CameraCapture()

    if not camera.cameras:
        print("[중단] 열린 카메라가 하나도 없습니다. 연결/인덱스를 확인하세요.")
        return

    input("\n[대기] 초음파 센서 트리거를 대신할 Enter 입력 대기 중... (Enter를 누르면 캡처 시작)")

    print("\n" + "=" * 60)
    print("2) 마이크 + 카메라(seat_1, seat_2) 동시 캡처 시작")
    print("=" * 60)

    results = {}
    threads = [
        threading.Thread(target=_run_mic_capture, args=(rbt.MIC_DIR, results)),
        threading.Thread(
            target=_run_camera_capture,
            args=(camera, "seat_1", TEST_CAPTURE_COUNT, TEST_CAPTURE_INTERVAL_SEC, results),
        ),
        threading.Thread(
            target=_run_camera_capture,
            args=(camera, "seat_2", TEST_CAPTURE_COUNT, TEST_CAPTURE_INTERVAL_SEC, results),
        ),
    ]

    for t in threads:
        t.start()

    # 셋 다 끝날 때까지 대기 (마이크는 STT까지 포함해서 끝나는 시점)
    for t in threads:
        t.join()

    camera.release()

    print("\n" + "=" * 60)
    print("3) 캡처 결과 확인")
    print("=" * 60)
    print(f"mic: {'성공' if results.get('mic') else '실패/스킵'}")
    print(f"seat_1: {results.get('seat_1') or '실패/스킵'}")
    print(f"seat_2: {results.get('seat_2') or '실패/스킵'}")

    if not results.get("seat_1") and not results.get("seat_2"):
        print("[중단] 저장된 카메라 캡처가 하나도 없습니다.")
        return

    print("\n" + "=" * 60)
    print("4) 저장된 파일 확인")
    print("=" * 60)
    for seat_id in ("seat_1", "seat_2"):
        d = results.get(seat_id)
        if d and os.path.isdir(d):
            files = sorted(os.listdir(d))
            print(f"[{d}] {len(files)}개 파일: {files}")

    if os.path.exists(rbt.MIC_DIR):
        mic_files = sorted(os.listdir(rbt.MIC_DIR))
        print(f"[{rbt.MIC_DIR}] {len(mic_files)}개 파일: {mic_files}")

    print("\n" + "=" * 60)
    print("5) 셋 다 끝났으니 한 번에 서버로 전송 (rpi_buffer_trigger 로직 그대로 사용)")
    print("=" * 60)
    result = rbt.trigger_decision()

    print("\n" + "=" * 60)
    print("6) 최종 결과")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()

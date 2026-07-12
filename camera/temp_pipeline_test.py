"""
임시 통합 테스트 스크립트 (초음파 센서 대신 손으로 트리거)

목적:
1) 카메라 입력이 잘 들어오고, 캡처된 게 파일로 잘 저장되는지 확인
2) 저장된 파일들을 rpi_buffer_trigger가 잘 읽어서 서버로 전달하는지 확인
3) 서버(Colab)가 판단해서 응답을 잘 돌려주는지 확인

같은 폴더에 capture_v2.py, rpi_buffer_trigger_v2.py가 있어야 합니다.
(rpi_buffer_trigger_v2.py는 파일명을 rpi_buffer_trigger.py로 바꿔도 되고, 그대로 둬도 됩니다 -- 아래 import만 맞추면 됨)

테스트 속도를 위해 실제 운영값(60장, 3초 간격)보다 훨씬 줄여서 캡처합니다.
운영 전환 시 capture_series(count=60, interval_sec=3)로 되돌리면 됩니다.
"""

import os
from capture_v2 import CameraCapture
import rpi_buffer_trigger_v2 as rbt

# ============================================================
# 테스트 설정 -- NGROK_URL만 실제 서버 값으로 채우면 됩니다
# ============================================================

rbt.NGROK_URL = "https://xxxx-xx-xx-xxx-xx.ngrok-free.app"
rbt.DECIDE_ENDPOINT = f"{rbt.NGROK_URL}/decide"

rbt.CAMERA_DIR = "./captures"      # capture_v2.py의 기본 저장 위치와 동일
rbt.MIC_DIR = "./mic_logs_test"    # 지금은 마이크 없이 카메라만 테스트 (폴더 없어도 에러 안 남)

# 테스트용 축소 캡처 설정 (운영 시 60/3으로 되돌릴 것)
TEST_CAPTURE_COUNT = 3
TEST_CAPTURE_INTERVAL_SEC = 1


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
    print("2) 좌석별 캡처 실행 (테스트용: 짧게)")
    print("=" * 60)
    saved_dirs = []
    for seat_id in camera.SEAT_CAMERA_MAP:
        if seat_id not in camera.cameras:
            print(f"[건너뜀] {seat_id} 카메라가 열려있지 않음")
            continue
        out_dir = camera.capture_series(
            seat_id, count=TEST_CAPTURE_COUNT, interval_sec=TEST_CAPTURE_INTERVAL_SEC
        )
        if out_dir:
            saved_dirs.append(out_dir)

    camera.release()

    if not saved_dirs:
        print("[중단] 저장된 캡처가 없습니다. 카메라/저장 경로를 확인하세요.")
        return

    print("\n" + "=" * 60)
    print("3) 저장된 파일 확인")
    print("=" * 60)
    for d in saved_dirs:
        files = sorted(os.listdir(d))
        print(f"[{d}] {len(files)}개 파일: {files}")

    print("\n" + "=" * 60)
    print("4) 저장된 파일을 읽어서 서버로 전송 (rpi_buffer_trigger 로직 그대로 사용)")
    print("=" * 60)
    result = rbt.trigger_decision()

    print("\n" + "=" * 60)
    print("5) 최종 결과")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()

import cv2
import base64
import time
import json
import os


class CameraCapture:
    """
    Camera capture module
    person_1 / person_2 각각 카메라로 정면 촬영
    트리거 발생 시 3초 간격으로 60장을 개별 JSON 파일로 저장
    """

    # 카메라 위치 매핑 (사람 기준)
    PERSON_CAMERA_MAP = {
        "person_1": 0,
        "person_2": 1
    }

    def __init__(self):
        self.cameras = {}

        for person_id, index in self.PERSON_CAMERA_MAP.items():
            cap = cv2.VideoCapture(index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            if not cap.isOpened():
                print(f"[WARNING] Failed to open camera for {person_id} (index={index})")
            else:
                self.cameras[person_id] = cap
                print(f"[OK] Camera initialized for {person_id} (index={index})")

        time.sleep(1)

    def _capture_single_frame(self, person_id):
        """프레임 한 장 찍어서 base64로 변환 (내부용)"""
        cap = self.cameras[person_id]
        ret, frame = cap.read()

        if not ret:
            print(f"[ERROR] Frame capture failed - person_id: {person_id}")
            return None

        success, buffer = cv2.imencode(
            '.jpg', frame,
            [cv2.IMWRITE_JPEG_QUALITY, 85]
        )

        if not success:
            print(f"[ERROR] JPEG encoding failed - person_id: {person_id}")
            return None

        return base64.b64encode(buffer).decode('utf-8')

    def capture_series(self, person_id, count=60, interval_sec=3):
        """
        트리거 발생 시 호출되는 함수
        3초 간격으로 60장 캡처 → 각각 JSON 파일로 저장
        폴더 자동 생성
        """
        if person_id not in self.cameras:
            print(f"[ERROR] No camera registered for person_id: {person_id}")
            return None

        # 자동 폴더 생성 (타임스탬프 기반)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = f"captures/{person_id}_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        print(f"[OK] 폴더 생성: {output_dir}")

        for seq in range(count):
            image_base64 = self._capture_single_frame(person_id)

            if image_base64 is None:
                print(f"[WARNING] {seq}번째 캡처 실패, 건너뜀")
                continue

            payload = {
                "source": "camera",
                "person_id": person_id,  #기존 room_id에서 사람 id로 변경
                "image_base64": [image_base64],
                "ts": int(time.time() * 1000)
            }

            filename = os.path.join(output_dir, f"{person_id}_{seq:04d}.json")
            with open(filename, "w") as f:
                json.dump(payload, f)

            print(f"[OK] {filename} 저장 ({seq + 1}/{count})")

            if seq < count - 1:
                time.sleep(interval_sec)

        print(f"\n=== 완료! {output_dir}에 {count}개 JSON 파일 생성 ===")
        return output_dir

    def release(self):
        for person_id, cap in self.cameras.items():
            cap.release()
            print(f"[OK] Camera released - person_id: {person_id}")
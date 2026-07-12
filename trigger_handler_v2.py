import json
from capture import CameraCapture


class TriggerHandler:
    """
    v2.0 변경점:
    - Node A/B 두 개의 PIR AND 조건 -> 단일 좌석 센서의 seated_count >= 2 조건으로 변경
    - room_id 개념 없음 (공간이 하나뿐)
    """

    def __init__(self, camera: CameraCapture):
        self.camera = camera
        self.seated_count = 0

    def handle_sensor_signal(self, sensor_json_str):
        """
        좌석 센서(초음파)에서 온 신호 처리
        seated_count >= 2 일 때만 카메라 캡처 실행

        예상 입력:
        {"type":"sensor_update","seated_count":2,
         "seats":{"seat_1":{"distance_cm":34.2,"occupied":true},
                   "seat_2":{"distance_cm":29.8,"occupied":true}},
         "ts":1761264000000}
        """
        data = json.loads(sensor_json_str)
        self.seated_count = data.get("seated_count", 0)
        print(f"[신호 수신] seated_count={self.seated_count}")

        if self.seated_count >= 2:
            print("[트리거] 좌석 2개 이상 착석 감지 → 카메라 캡처 시작!")
            self._start_capture()
        else:
            print(f"[대기] 현재 착석 인원: {self.seated_count}")

    def _start_capture(self):
        """좌석별 카메라 순차 캡처 (동시 실행하고 싶으면 스레드/프로세스로 분리 필요)"""
        print("[캡처] seat_1 캡처 시작")
        self.camera.capture_series("seat_1", count=60, interval_sec=3)
        print("[캡처] seat_2 캡처 시작")
        self.camera.capture_series("seat_2", count=60, interval_sec=3)

        # 캡처 완료 후 상태 초기화 (다음 트리거를 위해)
        self.seated_count = 0
        print("[완료] 좌석 상태 초기화")

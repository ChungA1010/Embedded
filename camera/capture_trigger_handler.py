import json
from capture import CameraCapture


class TriggerHandler:

    def __init__(self, camera: CameraCapture):
        self.camera = camera
        self.pir_status = {
            "A": 0,  # 아두이노 A (seat_1)
            "B": 0   # 아두이노 B (seat_2)
        }

    # 아두이노 A,B에서 온 신호가 두 개 다 pir== 1일때만 캡처 실행
    def handle_sensor_signal(self, sensor_json_str):
        """
        아두이노 A 또는 B에서 온 신호 처리
        둘 다 pir == 1 일 때만 카메라 캡처 실행
        """

        """
        {"node":"A",
	        "type":"sensor_update",
	        "room_id":"room_demo",
	        "pir":1,
	        "temp_c":26.4,
	        "humidity_pct":41.2,
	        "activity":0.18,
	        "ts":1761264000000} 라는 데이터를 받았다고 가정
        """ 

        data = json.loads(sensor_json_str)

        node = data.get("node")       # "A" 또는 "B"
        pir = data.get("pir", 0)      # 0 또는 1

        # 해당 아두이노 PIR 상태 업데이트
        if node in self.pir_status:
            self.pir_status[node] = pir
            print(f"[신호 수신] Node {node} pir={pir}")

        # 둘 다 pir == 1 인지 확인
        if self.pir_status["A"] == 1 and self.pir_status["B"] == 1:
            print("[트리거] 두 좌석 모두 착석 감지 → 카메라 캡처 시작!")
            self._start_capture()
        else:
            print(f"[대기] 현재 상태: A={self.pir_status['A']}, B={self.pir_status['B']}")

    def _start_capture(self):
        """
        두 카메라 동시에 캡처 시작
        """
        print("[캡처] person_1 캡처 시작")
        self.camera.capture_series("person_1", count=60, interval_sec=3)

        print("[캡처] person_2 캡처 시작")
        self.camera.capture_series("person_2", count=60, interval_sec=3)

        # 캡처 완료 후 PIR 상태 초기화
        self.pir_status = {"A": 0, "B": 0}
        print("[완료] PIR 상태 초기화")


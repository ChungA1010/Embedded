"""
마이크로 5초 녹음해서 WAV 파일로만 저장 (서버 전송 없음).
녹음 자체가 잘 되는지, 재생해서 들어보고 확인하는 용도.
"""
import subprocess

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
ALSA_DEVICE = "hw:4,0"    # arecord -l 로 확인한 카드 번호로 맞추기
ALSA_CHANNELS = 1         # 채널 에러 나면 1로 바꿔보기
OUTPUT_PATH = "recorded_mic.wav"


def record():
    cmd = [
        "arecord",
        "-D", ALSA_DEVICE,
        "-f", "S16_LE",
        "-r", str(SAMPLE_RATE),
        "-c", str(ALSA_CHANNELS),
        "-d", str(RECORD_SECONDS),
        OUTPUT_PATH,
    ]
    print(f"녹음 중... ({RECORD_SECONDS}초)")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"arecord 실패: {result.stderr.strip()}")
    print(f"[OK] {OUTPUT_PATH} 저장 완료")
    print(f"재생하려면: aplay {OUTPUT_PATH}")


if __name__ == "__main__":
    input("Enter를 누르면 녹음을 시작합니다...")
    record()

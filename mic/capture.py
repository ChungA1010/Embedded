"""
마이크 캡처 + loudness_db 측정 + STT -> JSON 반환 및 파일 저장
함수: capture_audio() -> dict
      save_mic_entry(entry, mic_dir) -> None
      capture_and_save(mic_dir) -> dict   (캡처 + 저장을 한 번에)

v2.0 변경점:
- room_id 제거 (공용 마이크 1개, 공간 구분 없음)
- 캡처 결과를 MIC_DIR의 jsonl 파일에 append하는 저장 로직 추가
  (rpi_buffer_trigger_v2.py의 read_mic_window()가 이 파일을 스캔함)
"""
import json
import os
import time
import numpy as np
import sounddevice as sd
from mic.stt import transcribe

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
LOUDNESS_THRESHOLD_DB = 45.0  # 이 값 이상이면 speech_detected=True


def _record_pcm(duration: int = RECORD_SECONDS) -> np.ndarray:
    audio = sd.rec(int(SAMPLE_RATE * duration), samplerate=SAMPLE_RATE,
                    channels=1, dtype="float32")
    sd.wait()
    return audio.flatten()


def _calc_loudness_db(y: np.ndarray) -> float:
    rms = np.sqrt(np.mean(y ** 2))
    if rms < 1e-10:
        return 0.0
    # sounddevice float32는 [-1, 1] 범위 -> dBFS 기준으로 +94 보정해 dB SPL 근사
    return round(20 * np.log10(rms) + 94.0, 1)


def capture_audio() -> dict:
    """
    마이크로 5초 녹음 -> loudness 계산 -> (필요 시) STT까지 실행해서 dict로 반환.
    파일 저장은 안 함 (save_mic_entry 또는 capture_and_save를 따로 호출해야 함).

    Returns:
        {
          "source": "mic",
          "speech_detected": bool,
          "loudness_db": float,
          "transcript": str,
          "ts": int  (Unix epoch ms)
        }
    """
    y = _record_pcm()
    loudness_db = _calc_loudness_db(y)
    speech_detected = loudness_db >= LOUDNESS_THRESHOLD_DB

    transcript = ""
    if speech_detected:
        transcript = transcribe(y, sample_rate=SAMPLE_RATE)

    return {
        "source": "mic",
        "speech_detected": speech_detected,
        "loudness_db": loudness_db,
        "transcript": transcript,
        "ts": int(time.time() * 1000),
    }


def save_mic_entry(entry: dict, mic_dir: str) -> str:
    """entry를 mic_dir/mic.jsonl에 한 줄 append. rpi_buffer_trigger_v2.py가 이 폴더를 스캔함."""
    os.makedirs(mic_dir, exist_ok=True)
    path = os.path.join(mic_dir, "mic.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def capture_and_save(mic_dir: str) -> dict:
    """캡처 + 저장을 한 번에. temp_pipeline_test.py 등에서 이 함수 하나만 호출하면 됨."""
    entry = capture_audio()
    path = save_mic_entry(entry, mic_dir)
    print(f"[OK] {path} 에 저장 (loudness_db={entry['loudness_db']}, "
          f"speech_detected={entry['speech_detected']})")
    if entry["speech_detected"]:
        print(f"     transcript: {entry['transcript']}")
    return entry

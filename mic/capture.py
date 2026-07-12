"""
마이크 캡처 -> WAV로 저장(base64) -> JSON 반환/파일 저장
v3 변경점: RPi4에서 STT를 하지 않음. 녹음만 하고 오디오 자체를 저장/전송.
           STT(Whisper)는 Colab 서버 쪽(decide())에서 처리함.

함수: capture_audio() -> dict
      save_mic_entry(entry, mic_dir) -> str
      capture_and_save(mic_dir) -> dict
"""
import io
import json
import os
import time
import wave
import base64
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
RECORD_SECONDS = 5
LOUDNESS_THRESHOLD_DB = 45.0  # 이 값 이상이면 speech_detected=True (참고용, 서버 전송은 항상 함)


def _record_pcm(duration: int = RECORD_SECONDS) -> np.ndarray:
    audio = sd.rec(int(SAMPLE_RATE * duration), samplerate=SAMPLE_RATE,
                    channels=1, dtype="float32")
    sd.wait()
    return audio.flatten()


def _calc_loudness_db(y: np.ndarray) -> float:
    rms = np.sqrt(np.mean(y ** 2))
    if rms < 1e-10:
        return 0.0
    return round(20 * np.log10(rms) + 94.0, 1)


def _pcm_to_wav_base64(y: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
    """float32 PCM -> 16bit WAV -> base64 문자열"""
    pcm16 = (y * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def capture_audio() -> dict:
    """
    마이크로 5초 녹음 -> loudness 계산 -> WAV(base64)로 변환해서 dict 반환.
    STT는 여기서 하지 않음 (Colab 서버에서 처리).

    Returns:
        {
          "source": "mic",
          "speech_detected": bool,
          "loudness_db": float,
          "audio_base64": str,   # WAV 파일 base64
          "ts": int  (Unix epoch ms)
        }
    """
    y = _record_pcm()
    loudness_db = _calc_loudness_db(y)
    speech_detected = loudness_db >= LOUDNESS_THRESHOLD_DB
    audio_b64 = _pcm_to_wav_base64(y)

    return {
        "source": "mic",
        "speech_detected": speech_detected,
        "loudness_db": loudness_db,
        "audio_base64": audio_b64,
        "ts": int(time.time() * 1000),
    }


def save_mic_entry(entry: dict, mic_dir: str) -> str:
    """entry를 mic_dir/mic.jsonl에 한 줄 append."""
    os.makedirs(mic_dir, exist_ok=True)
    path = os.path.join(mic_dir, "mic.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def capture_and_save(mic_dir: str) -> dict:
    """캡처 + 저장을 한 번에."""
    entry = capture_audio()
    path = save_mic_entry(entry, mic_dir)
    print(f"[OK] {path} 에 저장 (loudness_db={entry['loudness_db']}, "
          f"speech_detected={entry['speech_detected']}, "
          f"audio {len(entry['audio_base64'])}자)")
    return entry

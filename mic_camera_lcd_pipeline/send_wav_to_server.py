"""
record_wav_only.py 로 저장해둔 WAV 파일을 읽어서 Colab 서버로 전송.
녹음은 안 하고, 이미 있는 파일만 읽어서 보냄 -> 같은 녹음으로 반복 테스트하기 편함.
"""
import base64
import json
import wave
import numpy as np
import requests

WAV_PATH = "recorded_mic.wav"
NGROK_URL = "https://ancient-attentive-cursive.ngrok-free.dev"  # 실제 서버 URL로 교체
DECIDE_ENDPOINT = f"{NGROK_URL}/decide"


def _calc_loudness_db(path: str) -> float:
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-10:
        return 0.0
    return float(round(20 * np.log10(rms) + 94.0, 1))


def main():
    with open(WAV_PATH, "rb") as f:
        wav_bytes = f.read()
    audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
    loudness_db = _calc_loudness_db(WAV_PATH)

    payload = {
        "audio_base64": audio_b64,
        "loudness_db": loudness_db,
    }

    print(f"전송할 payload: audio_base64 ({len(audio_b64)}자, 생략), loudness_db={loudness_db}")

    res = requests.post(DECIDE_ENDPOINT, json=payload, timeout=120)
    print(f"status: {res.status_code}")
    print(json.dumps(res.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

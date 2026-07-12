"""
STT 모듈 -- Whisper 로컬 또는 OpenAI Whisper API 선택
USE_API = False  -> 로컬 Whisper (RPi4에서 느림, 인터넷 불필요)
USE_API = True   -> OpenAI Whisper API (빠름, 인터넷 필요, 유료, API 키 필요)
"""
import numpy as np

USE_API = True                # 클라우드 STT API 사용 (RPi4 로컬 처리 없음)
OPENAI_API_KEY = ""           # <-- 여기에 실제 OpenAI API 키 입력 필요 (없으면 API 호출 시 에러)
WHISPER_MODEL_SIZE = "base"   # tiny / base / small

_local_model = None


def _load_local_model():
    global _local_model
    if _local_model is None:
        import whisper
        _local_model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _local_model


def transcribe(y: np.ndarray, sample_rate: int = 16000) -> str:
    if USE_API:
        return _transcribe_api(y, sample_rate)
    return _transcribe_local(y)


def _transcribe_local(y: np.ndarray) -> str:
    model = _load_local_model()
    result = model.transcribe(y.astype(np.float32), language="ko", fp16=False)
    return result["text"].strip()


def _transcribe_api(y: np.ndarray, sample_rate: int) -> str:
    import io
    import wave
    import openai

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 비어있습니다. mic/stt.py에서 설정하세요.")

    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    # float32 -> 16-bit PCM WAV (in-memory)
    pcm = (y * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    buf.seek(0)
    buf.name = "audio.wav"

    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
        language="ko",
    )
    return transcript.text.strip()

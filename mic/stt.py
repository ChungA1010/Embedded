"""
STT 모듈 — Colab에서 실행. mic/stt_server.py의 POST /stt가 이 함수를 감싸서 씀.

RPi4의 mic/capture.py는 STT를 하지 않고 audio_base64(WAV)만 mic.jsonl에 저장하고,
트리거 시점에 rpi_buffer_trigger(통합 담당)가 /stt를 호출해서 transcript를 받아감.
이 파일 자체는 RPi4가 아니라 Colab 세션에 올려서 사용합니다.
"""
import base64
import os
import tempfile

WHISPER_MODEL_SIZE = "medium"  # Colab GPU 기준. tiny/base/small/medium/large-v3

_model = None


def _load_model():
    global _model
    if _model is None:
        import whisper
        _model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _model


def transcribe_audio_base64(audio_base64: str, language: str = "ko") -> str:
    """
    RPi4가 보낸 audio_base64(WAV base64 문자열) -> 한국어 transcript.
    audio_base64가 비어 있으면 빈 문자열 반환 (그 트리거에 발화가 없어
    사진만으로 판단해야 하는 케이스 — 명세서 "transcript 없으면 사진만으로 판단").
    """
    if not audio_base64:
        return ""

    import torch

    model = _load_model()
    wav_bytes = base64.b64decode(audio_base64)

    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(wav_bytes)
        result = model.transcribe(path, language=language, fp16=torch.cuda.is_available())
    finally:
        os.remove(path)

    return result["text"].strip()

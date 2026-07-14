"""
Colab에서 띄우는 STT 전용 서버.

mic/capture.py가 녹음 직후 이 서버의 POST /stt로 오디오(WAV base64)를 보내면
mic/stt.py의 Whisper로 변환한 transcript를 바로 돌려줌.
(사진 판단/최종 결정을 하는 /decide와는 별개의, STT만 담당하는 엔드포인트)

Colab에서 실행하는 방법 (노트북 셀 예시):
    !pip install -q fastapi uvicorn pyngrok openai-whisper nest-asyncio
    # mic/stt.py, mic/stt_server.py를 세션에 업로드한 뒤:

    import nest_asyncio, uvicorn
    from pyngrok import ngrok
    nest_asyncio.apply()

    public_url = ngrok.connect(8000)
    print("STT_ENDPOINT =", public_url.public_url + "/stt")

    from mic.stt_server import app
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
from fastapi import FastAPI
from pydantic import BaseModel

from mic.stt import transcribe_audio_base64

app = FastAPI()


class STTRequest(BaseModel):
    audio_base64: str


class STTResponse(BaseModel):
    transcript: str


@app.post("/stt", response_model=STTResponse)
def stt(req: STTRequest) -> STTResponse:
    transcript = transcribe_audio_base64(req.audio_base64)
    return STTResponse(transcript=transcript)
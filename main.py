from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse
import uvicorn
import os
import shutil
import uuid
from dotenv import load_dotenv
from groq import Groq
from langchain_groq import ChatGroq
from helpers.stt import transcribe_audio
from helpers.tts import google_tts_play


load_dotenv()


api_key = os.getenv("GROQ_API_KEY")
# Setup Groq client
client = Groq(api_key=api_key)
llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.7)

app = FastAPI()

@app.post("/audio")
def receive_audio(file: UploadFile = File(...)):
    # Save uploaded audio
    os.makedirs("audio_chunks", exist_ok=True)
    file_path = os.path.join("audio_chunks", f"chunk_{uuid.uuid4().hex}.wav")
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)


    # Speech-to-text 
    text = transcribe_audio(client, file_path)

    # LLM response
    response =llm.invoke(text)

    bot_reply = response.content if response else "Sorry, I didn't catch that."

    # Text-to-speech → save to response.wav
    tts_path = "response.wav"
    google_tts_play(bot_reply, file_path=tts_path)

    # Return audio bytes directly
    def iterfile():
        with open(tts_path, "rb") as f:
            yield from f


    return StreamingResponse(iterfile(), media_type="audio/wav")




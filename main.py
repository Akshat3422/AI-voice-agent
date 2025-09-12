import asyncio
from fastapi import FastAPI, File, UploadFile,WebSocket, WebSocketDisconnect
from typing import Dict, Any
import json
import websockets # type: ignore
from fastapi.responses import StreamingResponse
import uvicorn
import os
import shutil
import tempfile
import uuid
from dotenv import load_dotenv
from groq import Groq
from langchain_groq import ChatGroq
from helpers.stt import transcribe_audio
from helpers.tts import google_tts_play
import random
from helpers.Prompt import build_system_prompt
from helpers.reponse import generate_response


load_dotenv()

router = FastAPI()


api_key = os.getenv("GROQ_API_KEY")
# Setup Groq client
client = Groq(api_key=api_key)
llm = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.7)

app = FastAPI()
CONVERSATIONS: Dict[str, Dict[str, Any]] = {}

# post request to upload text questions and return transcription
@app.post("/upload_questions/")
async def upload_questions(file: UploadFile = File(...)):
    try:
        content = await file.read()
        questions_data = content.decode("utf-8").splitlines()
        questions_data = [q.strip() for q in questions_data if q.strip()]
        router.default_questions = questions_data
        return {"status": "ok", "questions_count": len(questions_data)}
    except Exception as e:
        return {"error": str(e)}


# Viva API for WebSocket connections
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    session_id = str(uuid.uuid4())

    # Initialize session data
    CONVERSATIONS[session_id] = {
        "questions": [],
        "asked_idxs": set(),
        "history": [],
        "last_question": None,
        "audio_chunks": [],
    }
    state = CONVERSATIONS[session_id]
    initialized = False

    try:
        while True:
            message = await websocket.receive()

            # Handle audio chunks
            if "bytes" in message and message["bytes"] is not None:
                state["audio_chunks"].append(message["bytes"])
                continue

            # Handle text messages
            if "text" in message and message["text"] is not None:
                data = json.loads(message["text"])
            else:
                continue

            event = data.get("event")

            if event == "start":
                questions = data.get("questions") or getattr(router, "default_questions", [])
                if not questions:
                    await websocket.send_text(json.dumps({
                        "event": "error",
                        "message": "No questions available. Please upload a questions file first."
                    }))
                    continue

                state["questions"] = questions
                state["history"].append({"role": "system", "content": "Viva started."})
                initialized = True
                await websocket.send_text(json.dumps({"type": "started", "session_id": session_id}))

                # Pick a random first question
                unasked_idxs = [i for i in range(len(state["questions"])) if i not in state["asked_idxs"]]
                if unasked_idxs:
                    first_idx = random.choice(unasked_idxs)
                    first_q = state["questions"][first_idx]
                    state["asked_idxs"].add(first_idx)
                    state["last_question"] = first_q
                    state["history"].append({"role": "system", "content": first_q})
                    await websocket.send_text(json.dumps({"event": "question", "text": first_q}))

            elif event == "end_utterance":
                if not initialized:
                    initialized = True
                    state["history"].append({"role": "system", "content": "Viva auto-started."})

                # Save audio chunks to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    for chunk in state["audio_chunks"]:
                        tmp.write(chunk)
                    tmp_path = tmp.name
                state["audio_chunks"].clear()

                # Transcribe audio safely
                transcription = await asyncio.to_thread(transcribe_audio, tmp_path)
                os.remove(tmp_path)

                if not transcription:
                    await websocket.send_text(json.dumps({
                        "event": "error",
                        "message": "Transcription failed."
                    }))
                    continue

                state["history"].append({"role": "user", "content": transcription})
                await websocket.send_text(json.dumps({"event": "transcription", "text": transcription}))

                # Prepare prompts
                system_prompt = build_system_prompt(state["questions"])
                next_question_idx = None
                unasked_idxs = [i for i in range(len(state["questions"])) if i not in state["asked_idxs"]]
                if unasked_idxs:
                    next_question_idx = random.choice(unasked_idxs)

                user_prompt = {
                    "student_last_answer": transcription,
                    "next_predefined_question": state["questions"][next_question_idx] if next_question_idx is not None else None,
                    "conversation_history": json.dumps(state['history'][-10:], ensure_ascii=False)
                }

                # Generate assistant response
                response_text = await asyncio.to_thread(generate_response, system_prompt, user_prompt)
                state["history"].append({"role": "assistant", "content": response_text})
                await websocket.send_text(json.dumps({"event": "response", "text": response_text}))

                # TTS playback
                audio_bytes = await google_tts_play(response_text)
                if audio_bytes:
                    CHUNK_SIZE = 512 * 1024
                    for i in range(0, len(audio_bytes), CHUNK_SIZE):
                        await websocket.send_bytes(audio_bytes[i:i + CHUNK_SIZE])
                    await websocket.send_text(json.dumps({"type": "audio_end"}))
                else:
                    await websocket.send_text(json.dumps({"type": "audio_failed"}))

                # Pick next random question
                if next_question_idx is not None:
                    state["asked_idxs"].add(next_question_idx)
                    next_q = state["questions"][next_question_idx]
                    state["last_question"] = next_q
                    state["history"].append({"role": "system", "content": next_q})
                    await websocket.send_text(json.dumps({"event": "question", "text": next_q}))

            elif event == "end_session":
                await websocket.send_text(json.dumps({"type": "session_ended"}))
                break

            elif event == "get_state":
                safe_state = {
                    "session_id": session_id,
                    "questions_count": len(state["questions"]),
                    "asked_count": len(state["asked_idxs"]),
                }
                await websocket.send_text(json.dumps({"type": "state", "state": safe_state}))
                continue

    except WebSocketDisconnect:
        print(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        print("Unexpected error:", e)
    finally:
        CONVERSATIONS.pop(session_id, None)











        
        


















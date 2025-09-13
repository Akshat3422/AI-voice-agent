import asyncio
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional
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

CONVERSATIONS: Dict[str, Dict[str, Any]] = {}

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "active_sessions": len(CONVERSATIONS)}

@router.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Viva WebSocket Server", "websocket_endpoint": "/ws"}

# post request to upload text questions and return transcription
@router.post("/upload_questions/")
async def upload_questions(file: UploadFile = File(...)):
    try:
        content = await file.read()
        questions_data = content.decode("utf-8").splitlines()
        questions_data = [q.strip() for q in questions_data if q.strip()]
        router.default_questions = questions_data
        return {"status": "ok", "questions_count": len(questions_data)}
    except Exception as e:
        return {"error": str(e)}

async def safe_websocket_receive(websocket: WebSocket, timeout: float = 0.1) -> Optional[dict]:
    """Safely receive WebSocket message with timeout to prevent blocking on disconnect"""
    try:
        # Use a very short timeout to avoid blocking
        message = await asyncio.wait_for(websocket.receive(), timeout=timeout)
        return message
    except asyncio.TimeoutError:
        return None
    except WebSocketDisconnect:
        raise
    except Exception as e:
        error_str = str(e).lower()
        if any(keyword in error_str for keyword in ["disconnect", "closed", "connection", "broken"]):
            raise WebSocketDisconnect()
        raise

async def handle_websocket_message(websocket: WebSocket, session_id: str, state: dict, initialized: bool):
    """Handle individual WebSocket messages"""
    # Try to receive a message
    message = await safe_websocket_receive(websocket)
    if message is None:
        return initialized  # Timeout, no message available
    
    # Handle audio chunks (binary data)
    if "bytes" in message and message["bytes"] is not None:
        state["audio_chunks"].append(message["bytes"])
        return initialized

    # Handle text messages
    if "text" in message and message["text"] is not None:
        try:
            data = json.loads(message["text"])
        except json.JSONDecodeError:
            print(f"Invalid JSON received: {message['text']}")
            return initialized
    else:
        return initialized




    event = data.get("event")
    print(f"Received event: {event} for session: {session_id}")

    if event == "start":
        questions = data.get("questions") or getattr(router, "default_questions", [])
        if not questions:
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": "No questions available. Please upload a questions file first."
            }))
            return initialized
        
        state["questions"] = questions
        state["history"].append({"role": "system", "content": "Viva started."})
        initialized = True

        await websocket.send_text(json.dumps({
            "type": "started", 
            "session_id": session_id
        }))

        # Pick a random first question
        unasked_idxs = [i for i in range(len(state["questions"])) if i not in state["asked_idxs"]]
        if unasked_idxs:
            first_idx = random.choice(unasked_idxs)
            first_q = state["questions"][first_idx]
            state["asked_idxs"].add(first_idx)
            state["last_question"] = first_q
            state["history"].append({"role": "system", "content": first_q})
            
            await websocket.send_text(json.dumps({
                "event": "question", 
                "text": first_q
            }))

    elif event == "end_utterance":
        if not initialized:
            initialized = True
            state["history"].append({"role": "system", "content": "Viva auto-started."})

        if not state["audio_chunks"]:
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": "No audio data received."
            }))
            return initialized

        # Save audio chunks to temp file
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                for chunk in state["audio_chunks"]:
                    tmp.write(chunk)
                tmp_path = tmp.name
            state["audio_chunks"].clear()

            # Transcribe audio safely
            transcription = await asyncio.to_thread(transcribe_audio, tmp_path)
            
            if not transcription:
                await websocket.send_text(json.dumps({
                    "event": "error",
                    "message": "Transcription failed."
                }))
                return initialized

            state["history"].append({"role": "user", "content": transcription})
            await websocket.send_text(json.dumps({
                "event": "transcription", 
                "text": transcription
            }))

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
            await websocket.send_text(json.dumps({
                "event": "response", 
                "text": response_text
            }))


            # TTS playback
            try:
                audio_bytes = await google_tts_play(response_text)
                if audio_bytes:
                    CHUNK_SIZE = 512 * 1024
                    for i in range(0, len(audio_bytes), CHUNK_SIZE):
                        chunk = audio_bytes[i:i + CHUNK_SIZE]
                        await websocket.send_bytes(chunk)
                    await websocket.send_text(json.dumps({"type": "audio_end"}))
                else:
                    await websocket.send_text(json.dumps({"type": "audio_failed"}))
            except Exception as audio_error:
                print(f"TTS Error: {audio_error}")
                await websocket.send_text(json.dumps({"type": "audio_failed"}))

            # Pick next random question
            if next_question_idx is not None:
                state["asked_idxs"].add(next_question_idx)
                next_q = state["questions"][next_question_idx]
                state["last_question"] = next_q
                state["history"].append({"role": "system", "content": next_q})
                await websocket.send_text(json.dumps({
                    "event": "question", 
                    "text": next_q
                }))



        except Exception as processing_error:
            print(f"Audio processing error: {processing_error}")
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": f"Audio processing failed: {str(processing_error)}"
            }))
        finally:
            # Clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    elif event == "text_response":
        # Handle direct text responses
        text_content = data.get("text", "").strip()
        if not text_content:
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": "Empty text response."
            }))
            return initialized

        state["history"].append({"role": "user", "content": text_content})
        await websocket.send_text(json.dumps({
            "event": "transcription", 
            "text": text_content
        }))

        # Process similar to audio response
        system_prompt = build_system_prompt(state["questions"])
        next_question_idx = None
        unasked_idxs = [i for i in range(len(state["questions"])) if i not in state["asked_idxs"]]
        if unasked_idxs:
            next_question_idx = random.choice(unasked_idxs)

        user_prompt = {
            "student_last_answer": text_content,
            "next_predefined_question": state["questions"][next_question_idx] if next_question_idx is not None else None,
            "conversation_history": json.dumps(state['history'][-10:], ensure_ascii=False)
        }

        try:
            response_text = await asyncio.to_thread(generate_response, system_prompt, user_prompt)
            state["history"].append({"role": "assistant", "content": response_text})
            await websocket.send_text(json.dumps({
                "event": "response", 
                "text": response_text
            }))

            # Pick next question for text responses too
            if next_question_idx is not None:
                state["asked_idxs"].add(next_question_idx)
                next_q = state["questions"][next_question_idx]
                state["last_question"] = next_q
                state["history"].append({"role": "system", "content": next_q})
                await websocket.send_text(json.dumps({
                    "event": "question", 
                    "text": next_q
                }))

        except Exception as text_processing_error:
            print(f"Text processing error: {text_processing_error}")
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": f"Text processing failed: {str(text_processing_error)}"
            }))

    elif event == "end_session":
        await websocket.send_text(json.dumps({"type": "session_ended"}))
        raise WebSocketDisconnect()  # Trigger clean disconnect

    elif event == "get_state":
        safe_state = {
            "session_id": session_id,
            "questions_count": len(state["questions"]),
            "asked_count": len(state["asked_idxs"]),
            "initialized": initialized
        }
        await websocket.send_text(json.dumps({
            "type": "state", 
            "state": safe_state
        }))

    else:
        print(f"Unknown event received: {event}")

    return initialized

# Viva API for WebSocket connections
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    session_id = str(uuid.uuid4())
    
    try:
        await websocket.accept()
        print(f"WebSocket connected: {session_id} for client: {client_id}")
        
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

        # Main message processing loop with short intervals
        while True:
            try:
                initialized = await handle_websocket_message(websocket, session_id, state, initialized)
                # Small sleep to prevent busy waiting
                await asyncio.sleep(0.01)
            except WebSocketDisconnect:
                print(f"WebSocket disconnected: {session_id}")
                break
            except Exception as e:
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ["disconnect", "closed", "connection", "broken"]):
                    print(f"WebSocket connection lost: {session_id} - {e}")
                    break
                print(f"Error in message handler: {e}")
                continue

    except WebSocketDisconnect:
        print(f"WebSocket disconnected during setup: {session_id}")
    except Exception as e:
        print(f"Unexpected error in WebSocket endpoint: {e}")
    finally:
        # Clean up session data
        CONVERSATIONS.pop(session_id, None)
        print(f"Cleaned up session: {session_id}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
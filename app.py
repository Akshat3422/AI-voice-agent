import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase
import av
import wave
import tempfile
import requests

BACKEND_URL = "http://127.0.0.1:8000/audio"  # Your FastAPI endpoint

st.title("🎙️ Real-Time Voice Chatbot (Push-to-Send)")

# -------------------------
# Audio Recorder
# -------------------------
class AudioRecorder(AudioProcessorBase):
    def __init__(self):
        self.frames = []

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        # Convert to mono and append as bytes
        audio = frame.to_ndarray().mean(axis=0).astype("int16").tobytes()
        self.frames.append(audio)
        return frame

    def save_wav(self):
        if not self.frames:
            return None
        # Save full audio as one WAV
        tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp_file, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"".join(self.frames))
        self.frames = []
        return tmp_file.name

# -------------------------
# WebRTC streamer
# -------------------------
webrtc_ctx = webrtc_streamer(
    key="voice-chatbot",
    mode=WebRtcMode.SENDONLY,  # Only send audio, no local playback
    audio_processor_factory=AudioRecorder,
    media_stream_constraints={"audio": True, "video": False},
)

# -------------------------
# Send audio to backend
# -------------------------
if st.button("Send to Bot"):
    if webrtc_ctx.audio_processor:
        wav_file = webrtc_ctx.audio_processor.save_wav()
        if wav_file:
            with open(wav_file, "rb") as f:
                files = {"file": f}
                try:
                    response = requests.post(BACKEND_URL, files=files)
                    if response.status_code == 200:
                        st.audio(response.content, format="audio/wav")  # Only LLM TTS
                    else:
                        st.error(f"Backend error: {response.text}")
                except Exception as e:
                    st.error(f"Error connecting to backend: {e}")
        else:
            st.warning("No audio captured. Speak first.")

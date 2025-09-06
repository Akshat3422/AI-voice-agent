import streamlit as st
import requests
import pyttsx3
import os

BACKEND_URL = "http://127.0.0.1:8000/audio"  # Your FastAPI endpoint

st.title("🎙️ Real-Time Voice Chatbot (Text → Speech → Bot Reply)")

# -------------------------
# User Text Input
# -------------------------
text = st.text_area("Enter text to convert to speech:")

if st.button("Send to Bot"):
    if text.strip() == "":
        st.warning("⚠️ Please enter some text first.")
    else:
        # -------------------------
        # Convert text → speech.wav
        # -------------------------
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)   # Speed
        engine.setProperty("volume", 1)   # Volume
        speech_file = "speech.wav"
        engine.save_to_file(text, speech_file)
        engine.runAndWait()

        st.success("✅ speech.wav file created.")

        # -------------------------
        # Send audio to backend
        # -------------------------
        try:
            with open(speech_file, "rb") as f:
                files = {"file": ("speech.wav", f, "audio/wav")}
                response = requests.post(BACKEND_URL, files=files)

            if response.status_code == 200:
                st.audio(response.content, format="audio/wav")  # Bot’s reply (TTS)
            else:
                st.error(f"Backend error: {response.text}")
        except Exception as e:
            st.error(f"Error connecting to backend: {e}")

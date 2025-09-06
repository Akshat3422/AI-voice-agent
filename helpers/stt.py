def transcribe_audio(client, file_path: str) -> str:
    try:
        with open(file_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=f,
                model="whisper-large-v3-turbo",
                prompt="This is an English speech transcription.",
                response_format="text",   # simpler than verbose_json
                language="en"
            )
        return transcription
    except Exception as e:
        print("Error during transcription:", e)
        return ""

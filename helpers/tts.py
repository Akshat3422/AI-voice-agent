from gtts import gTTS
import simpleaudio as sa
from pydub import AudioSegment
import os

def google_tts_play(text: str, file_path="response.mp3"):
    try:
        # Generate TTS with Google
        tts = gTTS(text=text, lang="en")
        tts.save(file_path)  # saves as mp3

        # Convert mp3 to wav (since simpleaudio only plays wav reliably)
        wav_path = "response.wav"
        sound = AudioSegment.from_mp3(file_path)
        sound.export(wav_path, format="wav")

        # Play audio
        wave_obj = sa.WaveObject.from_wave_file(wav_path)
        play_obj = wave_obj.play()
        play_obj.wait_done()

        # Clean up (optional)
        os.remove(file_path)
        os.remove(wav_path)

    except Exception as e:
        print("Error in Google TTS/playback:", e)

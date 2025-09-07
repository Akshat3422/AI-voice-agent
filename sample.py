import pyttsx3

# Your speech text
text = "Tell me the about pec chandigarh college in India in 50 words"

# Initialize TTS engine
engine = pyttsx3.init()

# Set voice properties (optional)
engine.setProperty("rate", 150)   # Speed
engine.setProperty("volume", 1)   # Volume (0.0 to 1.0)

# Save as .wav file
engine.save_to_file(text, "speech.wav")
engine.runAndWait()

print("✅ speech.wav file has been created.")

import speech_recognition as sr
import pyttsx3
import google.generativeai as genai

# gemini key initialization and we can do it using os.load_dotenv()
genai.configure(api_key="AIzaSyBzb0Y__ixpknbSzjQDmxQtioYuq4KBLw0")

# Initialize speech recognizer and TTS engine

recognizer=sr.Recognizer()
tts=pyttsx3.init()

def speak(text):
    """Convert text to speech """
    tts.say(text)
    tts.runAndWait()

def listen():
    "Listen to the microphone input and return text "
    # we use with command to open our laptop's microphone 
    with sr.Microphone() as source:
        print("Listening...")
        audio=recognizer.listen(source)
        try:
            return recognizer.recognize_google(audio)
        except:
            return "Sorry I didn't catch that "
        
def ask_gemini(query):
    model=genai.GenerativeModel("gemini-2.0-flash")
    response=model.generate_content(query)
    return response.text

# Main Loop
while True:
    user_input=listen()
    print("You said :",user_input)

    if "exit" in user_input.lower():
        speak("GoodBye")
        break
    response=ask_gemini(user_input)
    print("AI :",response)
    speak(response)
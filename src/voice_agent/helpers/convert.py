from pydub import AudioSegment
import io


def save_as_wav(input_bytes: bytes, file_path: str):
    """Convert uploaded chunk (webm/ogg/opus) to valid wav file"""
    audio = AudioSegment.from_file(io.BytesIO(input_bytes))  # auto-detect format
    audio.export(file_path, format="wav")
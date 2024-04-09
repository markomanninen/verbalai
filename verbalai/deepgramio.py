# deepgramio.py - A Python module for streaming audio to text using Deepgram API.
# Native Python library imports
import os
import re
import time
from threading import Thread
from queue import Queue, Empty
# Load environment variables from a .env file
from dotenv import load_dotenv
load_dotenv()
# Installed packages
from pydub import AudioSegment
from pydub.playback import play
from deepgram import (
    DeepgramClient,
    SpeakOptions
)
# Library imports
# Import log lonfig as a side effect only
from .log_config import setup_logging
import logging
logger = logging.getLogger(__name__)

deepgram = DeepgramClient(os.getenv("DEEPGRAM_API_KEY"))

# DeepgramIO class
class DeepgramIO:
    """ A class for streaming audio to text using Deepgram API. """
    def __init__(self, remove_asterisks = True):
        """ Initialize the DeepgramIO class. """
        self.buffer = bytearray()
        # Start the playback thread
        self.audio_queue = Queue()
        self.playback_thread = Thread(target=self.playback_audio, daemon=True)
        self.playback_active = False
        self.playback_thread.start()
        self.remove_asterisks = remove_asterisks
    
    def playback_audio(self):
        """ Continuously play audio chunks from the queue. """
        while True:
            try:
                audio_chunk = self.audio_queue.get(block=True, timeout=1)
                if audio_chunk == "END OF STREAM":
                    break
                if audio_chunk:
                    if not self.playback_active:
                        logger.info(f"Start playback")
                        self.audio_stream_start = time.time()
                        self.playback_active = True
                    self.buffer.extend(audio_chunk.read())
                    audio_chunk.seek(0)
                    play(AudioSegment.from_mp3(audio_chunk))
                else:
                    # Empty audio chunk received, exit the loop.
                    # This should not happen too often.
                    print("Empty audio chunk received. Exit the loop")
                    break
            except Empty:
                continue
        self.playback_active = False
    
    def process(self, voice_id = "aura-asteria-en", model_id = "", text_stream = None, start_time = 0):
        """ Process the text stream and synthesize audio. """
        
        # Start the playback thread if it's not running
        # This ensures that the audio is played also from the second time and onwards
        if not self.playback_thread.is_alive():
            self.playback_active = False
            self.playback_thread = Thread(target=self.playback_audio, daemon=True)
            self.playback_thread.start()
        
        self.audio_stream_start, text_stream_start, connect_stream_start = 0, 0, 0
        
        def synthesize_audio(text):
            """ Synthesize audio from text. """
            nonlocal connect_stream_start
            if connect_stream_start == 0:
                connect_stream_start = time.time()
            self.audio_queue.put(
                deepgram.speak.v("1").stream(
                    {"text": text},
                    SpeakOptions(model=voice_id)
                ).stream
            )
        
        segment = ""
        for segment_text in text_stream():
            if not text_stream_start:
                text_stream_start = time.time()
            if "." == segment_text or "!" == segment_text or "?" == segment_text:
                synthesize_audio(re.sub(r'\*.*?\*', '', segment + segment_text) if self.remove_asterisks else (segment + segment_text))
                segment = ""
            else:
                segment += segment_text
        
        # Synthesize the rest of the segment
        if segment:
            synthesize_audio(re.sub(r'\*.*?\*', '', segment) if self.remove_asterisks else segment)
        
        self.audio_queue.put("END OF STREAM")
        
        logger.info(f"Connect stream start: {round(connect_stream_start - start_time, 6)} seconds.")
        logger.info(f"Text stream start: {round(text_stream_start - start_time, 6)} seconds.")
        logger.info(f"Audio stream start: {round(self.audio_stream_start - start_time, 6)} seconds.")
        
    def get_audio_bytes(self):
        """ Get the buffered wav audio data as bytes. """
        return self.buffer
    
    def cleanup(self):
        """ Cleanup the playback thread safely. """
        # Wait for the playback thread to finish
        while self.playback_active:
            time.sleep(0.1)
        self.buffer = bytearray()
        self.playback_thread.join(timeout=1)
    
    def quit(self):
        """ Cleanup playback thread. """
        self.cleanup()

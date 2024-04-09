# elevenlabsiomp3.py - A Python module for streaming text to speech using ElevenLabs API.
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed
from base64 import b64decode
from json import dumps, loads
from os import environ
from io import BytesIO
import time
import re
from threading import Thread
from queue import Queue, Empty
# Installed packages
from pydub import AudioSegment
from pydub.playback import play

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import log lonfig as a side effect only
from verbalai import log_config
import logging
logger = logging.getLogger(__name__)

# ElevenLabs API WebSocket URI
stream_uri = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id={model_id}{output_format}&optimize_streaming_latency=4"

# Extra headers (API KEY) for ElevenLabs API WebSocket connection
extra_headers = {
    'xi-api-key': environ.get('ELEVENLABS_API_KEY')
}

# ElevenLabs API WebSocket MP3 streaming class
class ElevenlabsIO:
    """ A Python class for streaming text to speech using ElevenLabs API. """
    def __init__(self, bit_rate=44100, sample_rate=128, frames_per_buffer=3200, audio_buffer_in_seconds=1, remove_asterisks = True):
        """ Initialize the ElevenlabsIO instance. """
        # Audio format parameters for mp3 output format
        self.bit_rate = bit_rate
        self.frames_per_buffer = frames_per_buffer
        self.sample_rate = sample_rate
        # Initial buffer size for audio data
        self.initial_buffer_size = self.bit_rate * 2 * audio_buffer_in_seconds
        self.buffer = bytearray()
        # Start the playback thread
        self.audio_queue = Queue()
        self.playback_thread = Thread(target=self.playback_audio, daemon=True)
        self.playback_active = False
        self.playback_thread.start()
        self.remove_asterisks = remove_asterisks
    
    def playback_audio(self):
        """Continuously play audio chunks from the queue."""
        while True:
            try:
                audio_chunk = self.audio_queue.get(block=True, timeout=1)
                if audio_chunk:
                    if audio_chunk == "END OF STREAM":
                        break
                    if not self.playback_active:
                        logger.info(f"Start playback")
                        self.audio_stream_start = time.time()
                        self.playback_active = True
                    self.buffer.extend(audio_chunk)
                    audio_segment = AudioSegment.from_file(BytesIO(audio_chunk), format="mp3")
                    play(audio_segment)
            except Empty:
                continue
        self.playback_active = False

    def process(self, voice_id, model_id, text_stream, start_time):
        """ Stream text chunks via WebSocket to ElevenLabs and play received audio in real-time. """
        global stream_uri, extra_headers
        
        output_format = f"&output_format=mp3_{self.bit_rate}_{self.sample_rate}"
        
        uri = stream_uri.format(voice_id=voice_id, model_id=model_id, output_format=output_format)
        
        # Start the playback thread if it's not running
        # This ensures that the audio is played also from the second time and onwards
        if not self.playback_thread.is_alive():
            self.playback_active = False
            self.playback_thread = Thread(target=self.playback_audio, daemon=True)
            self.playback_thread.start()
        
        self.audio_stream_start, text_stream_start, connect_stream_start = 0, 0, 0
        
        with connect(uri, additional_headers=extra_headers) as ws:
            
            connect_stream_start = time.time()
            
            ws.send(dumps(
                dict(
                    text=" ",
                    try_trigger_generation=True,
                    generation_config=dict(
                        chunk_length_schedule=[50],
                    ),
                )
            ))
            
            lasttime = None
            audio_buffer = b''
            totaltime = 0
            buffering = True
            
            def handle_audio_chunk(audio_chunk):
                """ Handle incoming audio chunks. """
                nonlocal audio_buffer, buffering, lasttime, totaltime
                if buffering:
                    # Accumulate audio data in the buffer
                    audio_buffer += audio_chunk
                    if len(audio_buffer) >= self.initial_buffer_size:
                        # Buffer has reached the initial threshold, start playback
                        self.audio_queue.put(audio_buffer)
                        audio_buffer = b''  # Reset the buffer for subsequent chunks
                        buffering = False  # Stop buffering, start real-time playback
                        logger.debug("Buffering complete, starting real-time playback.")
                else:
                    # Real-time playback mode, directly queue incoming chunks
                    self.audio_queue.put(audio_chunk)
                timediff = (time.time() - lasttime) if lasttime else 0
                totaltime += timediff
                lasttime = time.time()
                logger.debug(f"{round(timediff, 3)} Received audio chunk: {len(audio_chunk)} bytes.")
            
            def handle_response(response):
                """ Handle incoming responses from ElevenLabs API. """
                nonlocal audio_buffer
                if 'audio' in response and response['audio']:
                    audio_chunk = b64decode(response['audio'])
                    handle_audio_chunk(audio_chunk)
                elif response.get('isFinal', False):
                    # Elevenlab stream ended
                    # Handle any remaining audio in the buffer
                    if audio_buffer:
                        self.audio_queue.put(audio_buffer)
                        audio_buffer = b''
                    self.audio_queue.put("END OF STREAM")
                elif 'error' in response:
                    logger.warn(f"Elevenlabs websocket error: {response['message']}")
                else:
                    logger.warn(f"Elevenlabs unknown response: {response}")
            
            segment = ""
            # Stream text chunks
            for chunk in text_stream():
                if not text_stream_start:
                    text_stream_start = time.time()
                
                if "." == chunk or "!" == chunk or "?" == chunk:
                    # Send the text chunk to ElevenLabs API
                    ws.send(dumps({
                        # Remove any asterisk action indicators from the segment
                        "text": re.sub(r'\*.*?\*', '', segment + chunk) if self.remove_asterisks else (segment + chunk), 
                        "try_trigger_generation": True
                    }))
                    segment = ""
                else:
                    segment += chunk
                
                # Start receiving audio chunks already when the text is being sent
                try:
                    # The recv method is used to receive the next message from the WebSocket. 
                    # The argument 1e-4 is the timeout for receiving the message, in seconds. 
                    # If no message is received within this time, a TimeoutError is raised.
                    handle_response(loads(ws.recv(1e-4)))
                except TimeoutError:
                    pass
            
            # Rest of the text stream if it was not ended with . or ! or ?
            if segment:
                ws.send(dumps({
                    # Remove any asterisk action indicators from the segment
                    "text": re.sub(r'\*.*?\*', '', segment) if self.remove_asterisks else segment, 
                    "try_trigger_generation": True
                }))
                segment = ""
            
            # Signal end of text and trigger any remaining audio generation
            ws.send(dumps({"text": ""}))
            
            # Receive and play audio chunks as they arrive
            for message in ws:
                try:
                    handle_response(loads(message))
                except ConnectionClosed as e:
                    logger.warn(f"Elevenlabs websocket error: {e}")
        
        logger.info(f"Connect stream start: {round(connect_stream_start - start_time, 6)} seconds.")
        logger.info(f"Text stream start: {round(text_stream_start - start_time, 6)} seconds.")
        logger.info(f"Audio stream start: {round(self.audio_stream_start - start_time, 6)} seconds.")
    
    def get_audio_bytes(self):
        """ Get the buffered mp3 audio data as bytes. """
        return self.buffer
    
    def cleanup(self):
        """Cleanup the PyAudio stream more safely."""
        # Wait for the playback thread to finish
        while self.playback_active:
            time.sleep(0.1)
        self.buffer = bytearray()
        self.playback_thread.join(timeout=1)
    
    def quit(self):
        """ Cleanup playback thread. """
        self.cleanup()

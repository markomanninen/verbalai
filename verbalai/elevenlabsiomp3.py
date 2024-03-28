# elevenlabsio.py - A Python module for streaming text to speech using ElevenLabs API.
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed
from base64 import b64decode
from json import dumps, loads
from os import environ
from io import BytesIO
import time
import threading
from queue import Queue, Empty
from pydub import AudioSegment
from pydub.playback import play

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# ElevenLabs API WebSocket URI
stream_uri = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id={model_id}{output_format}&optimize_streaming_latency=4"

# Extra headers (API KEY) for ElevenLabs API WebSocket connection
extra_headers = {
    'xi-api-key': environ.get('ELEVEN_API_KEY')
}

# Chunker for text streaming
def text_chunker(chunks):
    """ Used during input streaming to chunk text blocks and set last char to space """
    splitters = (".", ",", "?", "!", ";", ":", "—", "-", "(", ")", "[", "]", "}", " ")
    buffer = ""
    for text in chunks:
        if buffer.endswith(splitters):
            yield buffer if buffer.endswith(" ") else buffer + " "
            buffer = text
        elif text.startswith(splitters):
            output = buffer + text[0]
            yield output if output.endswith(" ") else output + " "
            buffer = text[1:]
        else:
            buffer += text
    if buffer != "":
        yield buffer + " "

# ElevenLabs API WebSocket streaming class
class ElevenlabsIO:
    def __init__(self, bit_rate=44100, sample_rate=128, frames_per_buffer=3200, audio_buffer_in_seconds=2):
        """ Initialize the ElevenlabsIO instance. """
        # Audio format parameters for wav output format
        # bit rate
        self.bit_rate = bit_rate
        self.frames_per_buffer = frames_per_buffer
        self.sample_rate = sample_rate
        # Initial buffer size for audio data
        self.initial_buffer_size = (self.bit_rate * 1000 / 8) * audio_buffer_in_seconds
        self.buffer = bytearray()
        # Start the playback thread
        self.audio_queue = Queue()
        self.playback_thread = threading.Thread(target=self.playback_audio, daemon=True)
        self.playback_active = True
        self.playback_thread.start()
    
    def playback_audio(self):
        """Continuously play audio chunks from the queue."""
        while self.playback_active:
            try:
                audio_chunk = self.audio_queue.get(block=True, timeout=1)
                if audio_chunk:
                    self.buffer.extend(audio_chunk)
                    audio_segment = AudioSegment.from_file(BytesIO(audio_chunk), format="mp3")
                    play(audio_segment)
            except Empty:
                continue  # Loop will continue waiting for audio chunks

    def process(self, voice_id, model_id, text_stream):
        """ Stream text chunks via WebSocket to ElevenLabs and play received audio in real-time. """
        global stream_uri, extra_headers
        
        output_format = f"&output_format=mp3_{self.bit_rate}_{self.sample_rate}"
        
        uri = stream_uri.format(voice_id=voice_id, model_id=model_id, output_format=output_format)
        
        with connect(uri, additional_headers=extra_headers) as ws:
            
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
            
            # Stream text chunks
            for chunk in text_chunker(text_stream):
                ws.send(dumps({
                    "text": chunk, 
                    "try_trigger_generation": True
                }))
                try:
                    data = loads(ws.recv(1e-4))
                    if "audio" in data and data["audio"]:
                        audio_chunk = b64decode(data["audio"])
                        if buffering:
                            # Accumulate audio data in the buffer
                            audio_buffer += audio_chunk
                            if len(audio_buffer) >= self.initial_buffer_size:
                                # Buffer has reached the initial threshold, start playback
                                self.audio_queue.put(audio_buffer)
                                audio_buffer = b''  # Reset the buffer for subsequent chunks
                                buffering = False  # Stop buffering, start real-time playback
                        else:
                            # Real-time playback mode, directly queue incoming chunks
                            self.audio_queue.put(audio_chunk)
                except TimeoutError:
                    pass

            # Signal end of text and trigger any remaining audio generation
            ws.send(dumps({"text": ""}))

            # Receive and play audio chunks as they arrive
            for message in ws:
            #while True:
                try:
                    #response = loads(ws.recv())
                    response = loads(message)
                    if 'audio' in response and response['audio']:
                        # Decode the base64 audio chunk coming from Elevenlabs
                        audio_chunk = b64decode(response['audio'])
                        if buffering:
                            # Accumulate audio data in the buffer
                            audio_buffer += audio_chunk
                            if len(audio_buffer) >= self.initial_buffer_size:
                                # Buffer has reached the initial threshold, start playback
                                self.audio_queue.put(audio_buffer)
                                audio_buffer = b''
                                buffering = False
                        else:
                            # Real-time playback mode, directly queue incoming chunks
                            self.audio_queue.put(audio_chunk)
                        timediff = (time.time() - lasttime) if lasttime else 0
                        totaltime += timediff
                        lasttime = time.time()
                        print(f"{timediff} Received audio chunk: {len(audio_chunk)} bytes.")
                    elif response.get('isFinal', False):
                        # Elevenlab stream ended
                        # Handle any remaining audio in the buffer
                        if audio_buffer:
                            self.audio_queue.put(audio_buffer)
                            audio_buffer = b''
                    elif 'error' in response:
                        print(f"Elevenlabs websocket error: {response['message']}")
                    else:
                        print(f"Elevenlabs unknown response: {response}")
                except ConnectionClosed as e:
                    print(f"Elevenlabs websocket error: {e}")
            
            # Handle the rest of the audio buffer that might be left
            if audio_buffer:
                self.audio_queue.put(audio_buffer)
                audio_buffer = b''
    
    def get_audio_bytes(self):
        """ Get the buffered mp3 audio data as bytes. """
        self.buffer.seek(0)
        return self.buffer
    
    def cleanup(self):
        """Cleanup the PyAudio stream more safely."""
        # Check if the stream object exists and is open before calling is_active
        self.playback_active = False
        self.playback_thread.join()
    
    def quit(self):
        """ Cleanup and close the PyAudio instance. """
        self.cleanup()
# elevenlabsiomp3.py - A Python module for streaming text to speech using ElevenLabs API.
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed
from base64 import b64decode
from json import dumps, loads
from os import environ
from io import BytesIO
import time
from threading import Thread
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
    def __init__(self, bit_rate=44100, sample_rate=128, frames_per_buffer=3200, audio_buffer_in_seconds=1):
        """ Initialize the ElevenlabsIO instance. """
        # Audio format parameters for mp3 output format
        self.bit_rate = bit_rate
        self.frames_per_buffer = frames_per_buffer
        self.sample_rate = sample_rate
        # Initial buffer size for audio data
        self.initial_buffer_size = self.bit_rate * 10 * audio_buffer_in_seconds
        self.buffer = bytearray()
        # Start the playback thread
        self.audio_queue = Queue()
        self.playback_thread = Thread(target=self.playback_audio, daemon=True)
        self.playback_active = False
        self.playback_thread.start()
    
    def playback_audio(self):
        """Continuously play audio chunks from the queue."""
        while True:
            try:
                audio_chunk = self.audio_queue.get(block=True, timeout=1)
                if audio_chunk:
                    if audio_chunk == "END OF STREAM":
                        break
                    self.playback_active = True
                    self.buffer.extend(audio_chunk)
                    audio_segment = AudioSegment.from_file(BytesIO(audio_chunk), format="mp3")
                    play(audio_segment)
            except Empty:
                continue
        self.playback_active = False

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
                # Start receiving audio chunks already when the text is being sent
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
                                print("Buffering complete, starting real-time playback.")
                        else:
                            # Real-time playback mode, directly queue incoming chunks
                            self.audio_queue.put(audio_chunk)
                        timediff = (time.time() - lasttime) if lasttime else 0
                        totaltime += timediff
                        lasttime = time.time()
                        print(f"{round(timediff, 3)} Received audio chunk #1: {len(audio_chunk)} bytes {len(audio_buffer)}.")
                except TimeoutError:
                    pass

            # Signal end of text and trigger any remaining audio generation
            ws.send(dumps({"text": ""}))

            # Receive and play audio chunks as they arrive
            for message in ws:
                try:
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
                        #print(f"{round(timediff, 3)} Received audio chunk #2: {len(audio_chunk)} bytes.")
                    elif response.get('isFinal', False):
                        # Elevenlab stream ended
                        # Handle any remaining audio in the buffer
                        if audio_buffer:
                            self.audio_queue.put(audio_buffer)
                            audio_buffer = b''
                        self.audio_queue.put("END OF STREAM")
                    elif 'error' in response:
                        print(f"Elevenlabs websocket error: {response['message']}")
                    else:
                        print(f"Elevenlabs unknown response: {response}")
                except ConnectionClosed as e:
                    print(f"Elevenlabs websocket error: {e}")
    
    def get_audio_bytes(self):
        """ Get the buffered mp3 audio data as bytes. """
        return self.buffer
    
    def cleanup(self):
        """Cleanup the PyAudio stream more safely."""
        # Wait for the playback thread to finish
        while self.playback_active:
            time.sleep(0.1)
        self.playback_thread.join(timeout=1)
    
    def quit(self):
        """ Cleanup playback thread. """
        self.cleanup()
# elevenlabsio.py - A Python module for streaming text to speech using ElevenLabs API.
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed
from pyaudio import PyAudio, paInt16
from base64 import b64decode
from wave import open as open_wav
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
    def __init__(self, format=paInt16, channels=1, rate=24000, output_format="wav", frames_per_buffer=3200, audio_buffer_in_seconds=4):
        """ Initialize the ElevenlabsIO instance. """
        # Audio format parameters for wav output format
        self.format = format
        self.channels = channels
        self.rate = rate
        self.frames_per_buffer = frames_per_buffer
        self.stream = None
        self.audio = PyAudio() if output_format == "wav" else None
        # Initial buffer size for audio data
        # for instance, 4 second of audio is 128000 bytes <- paInt16 = 2 bytes * 1 channels * 16000 rate * 4 second
        self.initial_buffer_size = 2 * self.channels * self.rate * audio_buffer_in_seconds
        self.output_format = output_format
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
                    if self.output_format == "wav":
                        self.stream.write(audio_chunk)
                    else:
                        audio_segment = AudioSegment.from_file(BytesIO(audio_chunk), format="mp3")
                        play(audio_segment)
            except Empty:
                continue  # Loop will continue waiting for audio chunks

    def process(self, voice_id, model_id, text_stream):
        """ Stream text chunks via WebSocket to ElevenLabs and play received audio in real-time. """
        global stream_uri, extra_headers
        
        if (self.output_format == "mp3"):
            # Default format is mp3 which requires no additional parameters
            # TODO: Elevenlabs pro subscription has better quality options for mp3 however
            # which are not supported in this implementation
            output_format = ""
        else:
            # Wav format requires additional parameters for pcm sample rate
            output_format = f"&output_format=pcm_{self.rate}"
        
        uri = stream_uri.format(voice_id=voice_id, model_id=model_id, output_format=output_format)
        
        with connect(uri, additional_headers=extra_headers) as ws:
            
            if self.output_format == "wav":
                # Initialize PyAudio stream
                self.stream = self.audio.open(
                    format=self.format, 
                    channels=self.channels, 
                    rate=self.rate, 
                    output=True,
                    frames_per_buffer=self.frames_per_buffer
                )
            
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
        """ Get the buffered audio data as bytes. """

        if self.output_format == "mp3":
            self.buffer.seek(0)
            # Return the MP3 content
            return self.buffer

        # Save the buffered PCM data as a WAV content
        audio_content = BytesIO()
        with open_wav(audio_content, 'wb') as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(self.audio.get_sample_size(self.format))
            wav.setframerate(self.rate)
            wav.writeframes(bytes(self.buffer))
        # Ensure the buffer's pointer is at the beginning
        audio_content.seek(0)
        # Return the WAV content as bytes
        return audio_content.getvalue()
    
    def cleanup(self):
        """Cleanup the PyAudio stream more safely."""
        # Check if the stream object exists and is open before calling is_active
        self.playback_active = False
        self.playback_thread.join()
        if self.stream:
            try:
                if self.stream.is_active() or self.stream.is_stopped():
                    self.stream.stop_stream()
                    self.stream.close()
            except Exception as e:
                print(f"Error during stream cleanup: {e}")
            finally:
                self.stream = None
    
    def quit(self):
        """ Cleanup and close the PyAudio instance. """
        self.cleanup()
        if self.audio:
            self.audio.terminate()
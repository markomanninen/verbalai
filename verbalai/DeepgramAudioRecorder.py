# DeepgramAudioRecorder.py - A Python module for streaming audio to text using Deepgram API.
# Native Python library imports
import os
import time
import httpx
import threading
from json import dumps
from multiprocessing import Queue
# Load environment variables from a .env file
from dotenv import load_dotenv
load_dotenv()
# Installed packages
from deepgram import (
    DeepgramClient,
    LiveTranscriptionEvents,
    LiveOptions,
    FileSource,
    UrlSource,
    PrerecordedOptions,
    Microphone
)
# Library imports
# Import log lonfig as a side effect only
from .log_config import setup_logging
import logging
logger = logging.getLogger(__name__)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

deepgram: DeepgramClient = DeepgramClient(DEEPGRAM_API_KEY)

class AudioRecorder:
    """
    A class designed to facilitate background audio recording and processing, converting 
    spoken audio into text using speech recognition, and managing audio data for both 
    real-time processing and archiving.
    """
    
    def __init__(self, language="en-US"):
        """
        Initializes an instance of the AudioRecorder class, setting up necessary components 
        for audio recording, processing, and speech-to-text conversion.
        """
        
        self.language = language
        self.microphone = None
        
        self.utterance = ""
        self.last_word_end = 0
        self.first_word_start = 0
        
        self.dg_connection = deepgram.listen.live.v("1")
        # Register event listeners for the Deepgram connection
        self.dg_connection.on(LiveTranscriptionEvents.Open, self.on_open)
        self.dg_connection.on(LiveTranscriptionEvents.Transcript, self.on_message)
        self.dg_connection.on(LiveTranscriptionEvents.Metadata, self.on_metadata)
        self.dg_connection.on(LiveTranscriptionEvents.SpeechStarted, self.on_speech_started)
        self.dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, self.on_utterance_end)
        self.dg_connection.on(LiveTranscriptionEvents.Error, self.on_error)
        self.dg_connection.on(LiveTranscriptionEvents.Close, self.on_close)
        
        # Queue for storing incoming transcription tokens
        # and sending them to the message handler
        self.text_queue = Queue()
        # Not used in Deepgram implementation
        self.word_buffer = []
        self.previous_speaker = None

        self.active = True
        self.toggle_listener = True
        self.pause = False
        self.stop_listening = None
        self.streaming = False
        # Archive directory setup with a session-specific subdirectory
        self.archive_dir = "archive"
        self.session_dir = os.path.join(self.archive_dir, time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(self.session_dir, exist_ok=True)
    
    def on_open(self, dg, open, **kwargs):
        """ Callback function for incoming open events. """
        logger.info(f"Connection opened")
        if self.streaming:
            # Define a function to send KeepAlive messages to the server
            def keep_alive():
                last_keep_alive_time = time.time()
                start_time = time.time()
                while self.dg_connection:
                    # Send a KeepAlive message every 5 seconds
                    keep_alive_msg = dumps({"type": "KeepAlive"})
                    self.dg_connection.send(keep_alive_msg)
                    logger.debug("Sent KeepAlive message")
                    time.sleep(5)
                    now = time.time()
                    # Remind the user to press Enter to close the stream every 30 seconds
                    # This is particularly useful for long-running streams
                    # and when the stream has ended but the user has not pressed Enter
                    # to close the stream connection
                    if now - last_keep_alive_time > 30:
                        # Convert elapsed time into hours, minutes, and seconds
                        hours = int((now - start_time) // 3600)
                        minutes = int(((now - start_time) % 3600) // 60)
                        seconds = int((now - start_time) % 60)
                        print(f"[{hours:02d}:{minutes:02d}:{seconds:02d}] Press Enter to close the stream...")
                        last_keep_alive_time = now
            # Start a thread for sending KeepAlive messages
            keep_alive_thread = threading.Thread(target=keep_alive)
            keep_alive_thread.daemon = True
            keep_alive_thread.start()

    def on_message(self, dg, result, **kwargs):
        """ Callback function for incoming transcription tokens. """
        #sentence = result.channel.alternatives[0].transcript
        
        sentence = ""
        for word in result.channel.alternatives[0].words:
            if word.speaker and word.speaker != self.previous_speaker:
                sentence += f"(Speaker:{word.speaker}) "
                self.previous_speaker = word.speaker
            sentence += f"{word.word} "
        if len(sentence) == 0:
            return
        
        #print(sentence)
        
        if self.streaming and result.is_final:
            self.text_queue.put(sentence)
            self.utterance = ""
        else:
            if result.is_final:
                self.text_queue.put(sentence)
                self.utterance = ""
            else:
                self.utterance = sentence
        logger.debug("On message: %s", sentence)
        #logger.info(result)
        # Live view to incoming transciption tokens
        #print(f"> {sentence}", end="\r\n" if result.is_final and result.speech_final else "\r", flush=True)

    def on_metadata(self, dg, metadata, **kwargs):
        """ Callback function for incoming metadata. """
        logger.info(f"On metadata (duration: {metadata.duration})")
        if self.streaming and self.utterance:
            logger.debug(f"On metadata (utterance: {self.utterance}")
            self.text_queue.put(self.utterance)
            self.utterance = ""
        print(f"Speech duration: {metadata.duration}")

    def on_speech_started(self, dg, speech_started, **kwargs):
        """ Callback function for incoming speech start events. """
        self.first_word_start = speech_started["timestamp"]
        logger.info(speech_started)

    def on_utterance_end(self, dg, utterance_end, **kwargs):
        """ Callback function for incoming utterance end events. """
        #print(utterance_end, self.utterance)
        if self.utterance:
            logger.debug(f"On utterance end (utterance: {self.utterance}")
            self.text_queue.put(self.utterance)
            self.last_word_end = utterance_end["last_word_end"]
            self.utterance = ""

    def on_error(self, dg, error, **kwargs):
        """ Callback function for incoming error messages. """
        logger.error(error)

    def on_close(self, dg, close, **kwargs):
        """ Callback function for incoming close events. """
        if self.streaming and self.utterance:
            logger.debug(f"On close (utterance: {self.utterance}")
            self.text_queue.put(self.utterance)
            self.utterance = ""
        logger.info("Connection closed")
    
    def file_source(self, source, stream=True):
        """ Processes audio data from a file or URL for speech recognition. """
        try:
            if source.startswith(('http://', 'https://')):
                if stream:
                    self.stream_audio(source)
                else:
                    self.process_from_url(source)
            else:
                self.process_from_file(source)
        except Exception as e:
            logger.error(e)

    def stream_audio(self, source):
        self.streaming = True
        # Connect to websocket
        options = LiveOptions(
            model="nova-2",
            punctuate=True,
            language=self.language,
            #encoding="linear16",
            #channels=1,
            #sample_rate=16000,
            # To get UtteranceEnd, the following must be set:
            interim_results=True,
            utterance_end_ms="1000",
            vad_events=True,
            diarize=True,
        )
        
        if self.dg_connection.start(options) is False:
            print("Failed to start connection")
            return
    
        print(f"Streaming started {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("Press Enter to close the steam...")

        keep_alive_msg = dumps({"type": "KeepAlive"})
        self.dg_connection.send(keep_alive_msg)
        
        lock_exit = threading.Lock()
        exit = False

        # define a worker thread
        def myThread():
            with httpx.stream("GET", source) as r:
                for data in r.iter_bytes():
                    lock_exit.acquire()
                    if exit:
                        break
                    lock_exit.release()
                    if data and self.dg_connection:
                        self.dg_connection.send(data)

        # Start the worker thread
        myHttp = threading.Thread(target=myThread)
        myHttp.start()
        
        # Wait for the user to press Enter
        try:
            input("")
        except KeyboardInterrupt:
            raise
        
        # Stop the worker thread after the user presses Enter
        lock_exit.acquire()
        exit = True
        lock_exit.release()
        myHttp.join()
        self.dg_connection.finish()
        self.dg_connection = None
        
        print(f"Streaming ended {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def process_from_file(self, file_path):
        """ Processes audio data from a file for speech recognition. """
        # Read the file data into a buffer
        with open(file_path, "rb") as file:
            buffer_data = file.read()
        # Create a file source payload
        payload: FileSource = {
            "buffer": buffer_data,
        }
        # Configure Deepgram options for audio analysis
        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
        )
        # Call the transcribe_file method with the text payload and options
        response = deepgram.listen.prerecorded.v("1").transcribe_file(payload, options)
        # Print the response to buffer, queue, and log
        transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
        self.text_queue.put(transcript)
        logger.debug(f"Process from file: {transcript}")
        #print(response.to_json(indent=4))

    def process_from_url(self, url):
        """ Processes audio data from a URL for speech recognition. """
        # Create a URL source payload
        payload: UrlSource = {
            "url": url,
        }
        # Configure Deepgram options for audio analysis
        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
        )
        # Call the transcribe_url method with the text payload and options
        response = deepgram.listen.prerecorded.v("1").transcribe_url(payload, options)
        # Output the response to buffer, queue, and log
        transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
        self.text_queue.put(transcript)
        logger.debug(f"Process from URL: {transcript}")
        #print(response.to_json(indent=4))
    
    def start_listening(self, **kwargs):
        """
        Initiates the audio listening process, capturing audio input from the microphone in 
        the background and processing the audio data for speech recognition.
        """
        # Configure Deepgram options for live audio analysis
        options: LiveOptions = LiveOptions(
            model="nova-2",
            punctuate=True,
            language=self.language,
            encoding="linear16",
            channels=1,
            sample_rate=16000,
            # To get UtteranceEnd, the following must be set:
            interim_results=True,
            utterance_end_ms="1500",
            vad_events=True,
        )
        # Start the Deepgram connection
        self.dg_connection.start(options)
        # Create and start microphone
        self.microphone = Microphone(self.dg_connection.send)
        self.microphone.start()
        self.streaming = False

        if kwargs["feedback_word_buffer_limit"] > 0:
            print(f"# Every {kwargs["feedback_word_buffer_limit"]} words will be analyzed for a short feedback.")

        print("# Listening started. Feel free to speak your thoughts aloud.")
        
        try:
            # wait until finished
            input("############################################################\n> ")
        except KeyboardInterrupt:
            raise

        #if self.toggle_listener and not self.pause:
            #save_audio_to_file(wav_audio, "input", "wav")
        
    def cleanup(self):
        """
        Stops the audio listening process and cleans up resources associated with the Deepgram connection
        """
        # Stop the Deepgram microphone
        if self.microphone:
            self.microphone.finish()
        # Stop the Deepgram connection
        try:
            if self.dg_connection:
                self.dg_connection.finish()
        except Exception as e:
            logger.error(e)
        self.active = False

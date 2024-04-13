# GoogleSpeechAudioRecorder.py - A Python module for streaming audio to text using Google Speech Recognition API.
import os
import io
import time
import wave
import subprocess
import urllib.request
from queue import Empty
from multiprocessing import Process, Queue
from speech_recognition import (
    Recognizer, 
    Microphone, 
    AudioData, 
    UnknownValueError, 
    RequestError
)

# Load environment variables from a .env file
from dotenv import load_dotenv
load_dotenv()

# Import log lonfig as a side effect only
from .log_config import setup_logging
import logging
logger = logging.getLogger(__name__)

# Check if ffmpeg is installed
def is_ffmpeg_installed():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


# Additional imports for file and URL processing
try:
    from pydub import AudioSegment
    if not is_ffmpeg_installed():
        raise ImportError("ffmpeg is required for MP3 processing but not found. Download from: https://ffmpeg.org/")
except ImportError as e:
    AudioSegment = None
    ffmpeg_error = str(e)


def audio_processing_worker(input_queue, language, text_queue):
    """
    Processes audio data from an input queue using speech recognition and posts 
    the resulting text to a text queue.

    This worker function continuously retrieves audio data from an input queue, 
    attempts to convert it to text using Google's Speech Recognition API, and 
    then posts the recognized text to another queue for further processing. It 
    supports graceful termination by listening for a specific termination message 
    and handles exceptions related to speech recognition failures and request errors.

    Parameters:
    - input_queue (queue.Queue): A queue from which audio data tuples are retrieved. 
                                 Each tuple should contain (audio data, sample rate, 
                                 number of channels).
    - language (str): The language code to be used for speech recognition, e.g., 'en-US'.
    - text_queue (queue.Queue): A queue to which recognized text is posted.

    The function operates in an infinite loop, continuously polling the input queue 
    for new audio data until it encounters a termination message, "TERMINATE". Upon 
    receiving audio data, it initializes an `AudioData` object and uses the 
    `recognize_google` method of a `Recognizer` instance to perform speech recognition. 
    Recognized text is then posted to the text_queue. The function handles several 
    exceptions: it continues silently if the speech recognition service could not 
    understand the audio (`UnknownValueError`), logs errors related to service requests 
    (`RequestError`), and logs any other exceptions encountered during processing.

    Use Cases:
    - This function is designed to run in a separate thread or process, handling 
      speech-to-text conversion in the background while the main application performs 
      other tasks.
    - Suitable for real-time or near-real-time audio processing applications, such as 
      voice assistants, transcription services, or any system requiring asynchronous 
      speech-to-text conversion.
    """
    recognizer = Recognizer()
    while True:
        try:
            audio_data = input_queue.get(timeout=1)
            if audio_data == "TERMINATE":
                break
        except Empty:
            continue
        except KeyboardInterrupt:
            break

        if audio_data is None:
            break
        
        # Check if audio_data is a tuple and convert it to AudioData if necessary
        if isinstance(audio_data, tuple):
            audio_data = AudioData(audio_data[0], audio_data[1], audio_data[2])
        # Process the audio data with the Google Speech Recognition API
        try:
            text = recognizer.recognize_google(audio_data, language=language)
            if text:
                text_queue.put(text)
        except KeyboardInterrupt:
            break
        except UnknownValueError:
            # Google Speech Recognition could not understand the audio
            print('?', end='\r')
        except RequestError as e:
            logger.error(f"Could not request results from Google Speech Recognition service; {e}")
        except Exception as e:
            logger.error(f"Error processing audio; {e}")


class AudioRecorder:
    """
    A class designed to facilitate background audio recording and processing, converting 
    spoken audio into text using speech recognition, and managing audio data for both 
    real-time processing and archiving.

    The AudioRecorder class encapsulates functionality for capturing audio input from a 
    microphone, processing the audio data to recognize speech, and handling the 
    asynchronous flow of audio and text data through queues. It supports starting and 
    stopping audio capture, dynamically adjusting for ambient noise, and processing 
    audio input in real-time or near real-time. Additionally, it provides mechanisms 
    for archiving captured audio data and cleanly terminating background processing tasks.

    Attributes:
    - recognizer (speech_recognition.Recognizer): An instance used for converting audio 
                                                  to text.
    - language (str): The language code used for speech recognition.
    - audio_queue (queue.Queue): A queue for storing raw audio data to be processed.
    - text_queue (queue.Queue): A queue for storing recognized text from processed audio 
                                data.
    - word_buffer (list): A buffer for accumulating recognized words for further processing.
    - worker_process (multiprocessing.Process): A separate process for handling audio data 
                                                conversion to text.
    - active (bool): A flag indicating if the recorder is actively capturing and processing 
                     audio.
    - toggle_listener (bool): A flag for manually toggling the listening state on and off.
    - speaking (bool): A flag indicating if text-to-speech output is currently active.
    - archive_dir (str): The directory for storing archived audio files.
    - session_dir (str): A session-specific subdirectory for archiving audio files.

    The class provides methods to start listening (`start_listening`), stop listening and 
    cleanup resources (`cleanup`), and internal logic to support the background processing 
    of audio data, including speech recognition and file archiving. It is designed to be 
    used in applications that require real-time or near real-time speech-to-text conversion, 
    such as voice-controlled applications, audio monitoring systems, or interactive voice 
    response (IVR) systems.
    """
    
    def __init__(self, language="en-US"):
        """
        Initializes an instance of the AudioRecorder class, setting up necessary components 
        for audio recording, processing, and speech-to-text conversion.

        This constructor initializes the AudioRecorder class with configurations for speech 
        recognition, including setting the language for recognition and preparing queues for 
        audio data and processed text. It also starts a separate worker process for audio 
        processing, leveraging the audio_processing_worker function to convert audio data to 
        text in a non-blocking manner.

        Parameters:
        - language (str, optional): The language code to be used for speech recognition. 
                                    Defaults to 'en-US'.

        Attributes:
        - recognizer (speech_recognition.Recognizer): An instance of the Recognizer class 
                                                      used for speech recognition.
        - language (str): The language code for speech recognition.
        - audio_queue (queue.Queue): A queue for storing raw audio data to be processed.
        - text_queue (queue.Queue): A queue for storing processed text results from speech 
                                    recognition.
        - word_buffer (list): A buffer to accumulate words from processed text before further 
                              processing.
        - worker_process (multiprocessing.Process): A separate process dedicated to processing 
                                                    audio data
        from audio_queue and posting recognized text to text_queue.
        - active (bool): A flag indicating if the AudioRecorder instance is active.
        - toggle_listener (bool): A flag used to control the start and stop of audio listening.
        - speaking (bool): A flag indicating if text-to-speech output is currently speaking, 
                          to manage overlapping audio processes.
        - archive_dir (str): The base directory for archiving recorded audio.
        - session_dir (str): A session-specific subdirectory within archive_dir for storing 
                             session data.

        The constructor method sets up the environment for continuous audio processing and 
        recognition, including directory preparation for storing session data. The recognition 
        language and worker process configuration allow for flexible adaptation to different 
        languages and concurrent audio processing, ensuring that the main application thread 
        remains unblocked.
        """
        self.recognizer = Recognizer()
        self.language = language
        self.audio_queue = Queue()
        self.text_queue = Queue()
        self.word_buffer = []
        # Initialize the worker process for audio processing
        self.worker_process = Process(target=audio_processing_worker, args=(self.audio_queue, self.language, self.text_queue))
        self.active = True
        self.toggle_listener = True
        self.pause = False
        self.stop_listening = None
        # Archive directory setup with a session-specific subdirectory
        self.archive_dir = "archive"
        self.session_dir = os.path.join(self.archive_dir, time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(self.session_dir, exist_ok=True)
    
    def file_source(self, source, stream=False):
        """ Processes audio data from a file or URL for speech recognition. """
        self.worker_process.start()
        if source.startswith(('http://', 'https://')):
            self.process_from_url(source)
        else:
            self.process_from_file(source)
        self.audio_queue.put('TERMINATE')

    def process_from_file(self, file_path, file_in_chunks=True):
        """ Processes audio data from a file for speech recognition. """
        extension = os.path.splitext(file_path)[1].lower()
        if extension == '.wav':
            if file_in_chunks:
                self.process_wav_file_in_chunks(file_path)
            else:
                self.process_wav_file(file_path)
        elif extension == '.mp3':
            if not AudioSegment:
                raise ImportError("PyDub is required for MP3 processing but not installed.")
            if not is_ffmpeg_installed():
                raise ImportError("ffmpeg is required for MP3 processing but not found.")
            if file_in_chunks:
                self.process_mp3_file_in_chunks(file_path)
            else:
                self.process_mp3_file(file_path)
        else:
            raise ValueError("Unsupported file format.")

    def process_from_url(self, url):
        """ Processes audio data from a URL for speech recognition. """
        response = urllib.request.urlopen(url)
        data = response.read()
        content_type = response.headers.get('Content-Type')
        stream = io.BytesIO(data)
        if 'audio/wav' in content_type:
            self.process_wav_stream(stream)
        elif 'audio/mpeg' in content_type:
            if not AudioSegment:
                raise ImportError("pydub is required for MP3 processing but not installed.")
            if not is_ffmpeg_installed():
                raise ImportError("ffmpeg is required for MP3 processing but not found.")
            self.process_mp3_stream(stream)
        else:
            raise ValueError("Unsupported audio format from URL.")

    def process_wav_file_in_chunks(self, file_path, chunk_size=102400):
        """ Processes a WAV audio file in chunks for speech recognition. """
        with wave.open(file_path, 'rb') as wav_file:
            framerate = wav_file.getframerate()
            sampwidth = wav_file.getsampwidth()
            nchannels = wav_file.getnchannels()
            
            while True:
                frames = wav_file.readframes(chunk_size)
                if not frames:
                    break  # End of file reached
                
                # Convert frames to AudioData and enqueue for processing
                audio_data = AudioData(frames, framerate, sampwidth)
                self.audio_queue.put(audio_data)

    def process_wav_file(self, file_path):
        """ Processes a WAV audio file for speech recognition. """
        with open(file_path, 'rb') as f:
            self.process_wav_stream(f)
    
    def process_mp3_file_in_chunks(self, file_path, chunk_length=4096):
        """ Processes an MP3 audio file in chunks for speech recognition. """
        # Open the audio file using pydub
        audio_file = AudioSegment.from_file(file_path, format="mp3")
        
        # Calculate the total number of chunks
        total_chunks = len(audio_file) // chunk_length
        
        # Process each chunk individually
        for i in range(total_chunks + 1):
            start_ms = i * chunk_length
            end_ms = start_ms + chunk_length
            chunk = audio_file[start_ms:end_ms]
            
            # Ensure the chunk is mono and has the desired frame rate
            chunk = chunk.set_frame_rate(16000).set_channels(1)
            
            # Convert chunk to the format expected by the audio queue
            frames = chunk.get_array_of_samples()
            audio_data = AudioData(frames.tobytes(), chunk.frame_rate, chunk.sample_width)
            
            # Put the chunked audio data into the queue for processing
            self.audio_queue.put(audio_data)

    def process_mp3_file(self, file_path):
        """ Processes an MP3 audio file for speech recognition. """
        audio = AudioSegment.from_mp3(file_path)
        self.process_audio_segment(audio)

    def process_wav_stream(self, stream):
        """ Processes a WAV audio stream for speech recognition. """
        with wave.open(stream, 'rb') as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            audio_data = AudioData(frames, wav_file.getframerate(), wav_file.getsampwidth())
            self.audio_queue.put(audio_data)

    def process_mp3_stream(self, stream):
        """ Processes an MP3 audio stream for speech recognition. """
        audio = AudioSegment.from_file(stream, format="mp3")
        self.process_audio_segment(audio)

    def process_audio_segment(self, audio_segment):
        """ Processes an audio segment for speech recognition. """
        audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)
        frames = audio_segment.get_array_of_samples()
        audio_data = AudioData(frames.tobytes(), audio_segment.frame_rate, audio_segment.sample_width)
        self.audio_queue.put(audio_data)
    
    def start_listening(self, phrase_time_limit=5, feedback_word_buffer_limit=0, calibration_time=1, save_audio_to_file=None, **kwargs):
        """
        Initiates the audio listening process, capturing audio input from the microphone in 
        the background and processing the audio data for speech recognition.

        This method sets up a continuous listening service that captures audio through the 
        microphone and processes the audio data using a specified callback function. It 
        calibrates the microphone to adjust for ambient noise, starts the background 
        listening process, and initiates the worker process for audio processing. The method 
        ensures that audio data is processed only when specific conditions are met, such as 
        when listening has not been manually toggled off and when the system is not currently 
        speaking (to avoid capturing generated speech as input).

        The audio data captured during the listening session is put into an audio queue for 
        processing by the worker process and is also archived by saving it to a file. This 
        dual approach facilitates both real-time processing and the preservation of audio 
        data for future analysis or review.

        Additionally, this method provides feedback to the user about the listening status, 
        including calibration for ambient noise and the setting for phrase recognition time 
        limit. It also informs the user about the interaction controls for triggering final 
        inference and exiting the listening mode.
        """
        
        self.microphone = Microphone()
        with self.microphone as source:
            print(f"# Calibrating {calibration_time} seconds for ambient noise...")
            self.recognizer.adjust_for_ambient_noise(source, duration=calibration_time)
        
        def callback(recognizer, audio):
            if self.toggle_listener and not self.pause:
                wav_audio = audio.get_wav_data()
                audio_data = (wav_audio, audio.sample_rate, audio.sample_width)
                self.audio_queue.put(audio_data)
                if audio:
                    save_audio_to_file(wav_audio, "input", "wav")

        print(f"# Phrase recognition min time length is set to {phrase_time_limit} seconds.")
        self.stop_listening = self.recognizer.listen_in_background(self.microphone, callback, phrase_time_limit=phrase_time_limit)

        print("# Listening started. Feel free to speak your thoughts aloud.")
        if feedback_word_buffer_limit > 0:
            print(f"# Every {feedback_word_buffer_limit} words will be analyzed for a short feedback.")

        self.worker_process.start()

    def cleanup(self):
        """
        Stops the audio listening process and cleans up resources associated with the audio 
        processing.

        This method gracefully terminates the background audio listening and processing tasks. 
        It first stops the background listener that captures audio from the microphone, ensuring 
        that no further audio data is added to the processing queue. Then, it sends a termination 
        signal (in this case, `None`) to the audio processing queue, which the worker process 
        interprets as a command to stop processing and terminate. The method waits for the worker 
        process to join, ensuring that it has completed its execution and resources are properly 
        released. Finally, it sets the `active` flag of the AudioRecorder instance to `False`, 
        indicating that the instance is no longer actively listening or processing audio.

        This cleanup method is essential for ensuring that the application can shut down without 
        leaving orphaned processes or locked resources, making it critical for maintaining the 
        stability and reliability of the application, especially in long-running or complex 
        applications that may start and stop listening multiple times during their execution.
        """
        if self.stop_listening:
            self.stop_listening(wait_for_stop=True)
        self.audio_queue.put(None)
        if self.worker_process.is_alive():
            self.worker_process.join(timeout=1)
        self.active = False

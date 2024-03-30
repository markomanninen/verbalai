# verbalai.py - A Python script for near real-time voice-to-text, text to prompt text and text-to-speech interaction with an AI chatbot.
import os
import re
import sys
import time
import json
import argparse
import keyboard
import traceback
from queue import Empty
from threading import Thread
from anthropic import Anthropic
#from .elevenlabsio import ElevenlabsIO
from multiprocessing import Process, Queue
from colorama import init, Fore, Style, Back
from speech_recognition import Recognizer, Microphone, AudioData, UnknownValueError, RequestError

# Load environment variables from a .env file
from dotenv import load_dotenv
load_dotenv()

# ASCII Art for VerbalAI
ascii_art = """

██╗   ██╗███████╗██████╗ ██████╗  █████╗ ██╗      █████╗ ██╗
██║   ██║██╔════╝██╔══██╗██╔══██╗██╔══██╗██║     ██╔══██╗██║
██║   ██║█████╗  ██████╔╝██████╔╝███████║██║     ███████║██║
╚██╗ ██╔╝██╔══╝  ██╔══██╗██╔══██╗██╔══██║██║     ██╔══██║██║
 ╚████╔╝ ███████╗██║  ██║██████╔╝██║  ██║███████╗██║  ██║██║
  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝
                                                            
         Bidirectional Voice AI Chatbot - VerbalAI          

"""

# Initialize the colorama module for colored text output
init(autoreset=True)

# Global variables
default_input_voice_recognition_language = "en-US"
feedback_word_buffer_limit = 25
feedback_token_limit = 20
response_token_limit = 50
phrase_time_limit = 10
calibration_time = 2

# Debug mode flag
verbose = False

# Anthropic Claude GPT model
gpt_model = "claude-3-haiku-20240307"

# Available Anthropic Claude GPT models
available_models = [
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307"
]  

# Eleven Labs voice ID: Male voice (Drew)
voice_id = "29vD33N1CtxCmqQRPOHJ"

# Eleven Labs voice model ID
# eleven_monolingual_v1, eleven_multilingual_v1
voice_model_id = "eleven_multilingual_v2"

# Initialize the global ElevenlabsIO instance
elevenlabs_streamer = None

# Output format for the generated audio files
elevenlabs_output_format = "wav"  # mp3 or wav

# Output bit rate for the generated audio files
elevenlabs_output_bit_rate = 22050

# Output sample rate for the generated audio files
# Relevant only for the mp3 format
elevenlabs_output_sample_rate = 32

# Valid sample rates for WAV format
valid_wav_sample_rates = [16000, 22050, 24000, 44100]

# Valid combinations for MP3 format
valid_mp3_combinations = {
    22050: [32],
    44100: [32, 64, 96, 128, 192]
}

# Initialize Elevenlabs voice output and Google Speech Recognition disablers
disable_voice_output, disable_voice_recognition = False, False

# Chat username
username = "VerbalHuman"

# Initialize the audio recorder
audio_recorder = None

# Initialize the GPT client
# Note: dotenv handles the API key loading
gpt_client = Anthropic()

# Initialize the session message buffer
messages = []

# Initialize the meessage counter for monitoring the API request usage
inference_message_word_count = 0

# Keyboard shortcuts for controlling the chatbot
hotkey_pause     = "ctrl+alt+p" # Toggle response mode
hotkey_prompt    = "ctrl+alt+t" # Text prompt for the GPT model
hotkey_clear     = "ctrl+alt+c" # Clear the chat history
hotkey_feedback  = "ctrl+alt+f" # Activate short feedback
hotkey_summarize = "ctrl+alt+s" # Generate a summary of the conversation
hotkey_exit      = "ctrl+c"     # Exit the chatbot

# Summary and previous context summary file
summary, summary_file = "", ""

# System message part for the GPT model
short_mode = "You are currently in the short response mode. Respond to the user's input with a short one full complete sentence."

# System message part for the GPT model
long_mode = "You are currently in the long response mode. Respond to the user's input with a long detailed response."

previous_context = """

You can use the context from the previous conversation with the user to generate more coherent responses.

Summary of the previous discussions:

<<summary>>
"""

# System message template for the GPT model
system_message = """
You are VerbalAI chatbot implemented as a command-line tool. You can understand voice input with a voice-to-text recognition service, generate meaningful responses with your internal GPT model and speak responses to user via text-to-speech service.

You have two modes in responding: 1) a short response mode for the intermediate feedback / quick dialogue and 2) a long detailed response mode for the final feedback.

<<mode>>

Restrictions: Do NOT use asterisk action / tone indicators / emotes similar to *listening* or *whispering*, etc. in your response.

You are speaking with: <<user>>
Date and time is now: <<datetime>>
<<previous_context>>
"""

# Generate a summary -prompt
summary_generator_prompt = """
Generate a summary of the conversation given below:

<<summary>>
"""

###################################################
# CONSOLE MAGIC
###################################################

def blink_cursor():
    # Enable cursor blinking right after feedback
    sys.stdout.write('\033[?12h')
    sys.stdout.flush()


def freeze_cursor():
    # Disable cursor blinking
    sys.stdout.write('\033[?12l')
    sys.stdout.flush()


def invert_text(text):
    """ Inverts the text color and background color for a given text string. """
    return Back.RED + Style.BRIGHT + Fore.BLACK + text + Style.RESET_ALL


###################################################
# LANGUAGE INFERENCE
###################################################

def prompt(text, final=False):
    """
    Processes and displays a given text input in the chat system, and optionally 
    initiates a text-to-speech conversion of the generated response.

    This function modifies the global chat history, updates message counters, and 
    manages the interaction with the GPT API for generating responses. It conditionally 
    triggers a text-to-speech conversion for the final response.

    Parameters:
    - text (str): The input text to be processed and added to the chat history.
    - final (bool, optional): A flag indicating whether the input is the final one, 
                              affecting the mode of response generation and potentially 
                              initiating text-to-speech conversion.
      Defaults to False.

    Global Variables:
    - inference_message_word_count (int): A counter for the total word count of messages 
                                          processed. This is a direct indication of the 
                                          GPT API usage and relates to context window size 
                                          and token limits.
    - gpt_model: The GPT model used for generating responses.
    - system_message (str): Template for system messages including current mode 
                            and user information.
    - messages (list): The history of messages in the chat, both from the user and the 
                       system.
    - short_mode (str): The operation mode for non-final inputs.
    - long_mode (str): The operation mode for final inputs.
    - username (str): The name of the user in the chat.
    - response_token_limit (int): The maximum number of tokens for a final response.
    - feedback_token_limit (int): The maximum number of tokens for a non-final feedback 
                                  response.
    - voice_model_id (str): The ID of the voice model used for text-to-speech conversion.

    Returns:
    - str: The generated response to the input text, for logging or further processing.
    """
    
    global inference_message_word_count, gpt_model, system_message, messages, short_mode, long_mode, username, response_token_limit, feedback_token_limit, voice_model_id, elevenlabs_streamer, disable_voice_output, verbose
    
    text = text.strip()
    
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"].append({"type": "text", "text": text})
    else:
        messages.append({
            "role": "user", 
            "content": [{"type": "text", "text": text}]
        })
    
    inference_message_word_count += len(text.split(" "))
    # Generate the system message with the current mode, username, datetime, and previous context
    system = system_message.replace("<<mode>>", long_mode if final else short_mode).replace("<<user>>", username).replace("<<datetime>>", time.strftime("%Y-%m-%d %H:%M:%S")).replace("<<previous_context>>", previous_context.replace("<<summary>>", summary) if summary else "")
    
    with gpt_client.messages.stream(
        model = gpt_model,
        messages = messages,
        max_tokens = response_token_limit if final else feedback_token_limit,
        system = system
    ) as gpt_stream:

        response = ""
        
        # Freezed cursor indicates that system is outputting, not waiting for an input
        freeze_cursor()
        
        # Print the current time and the user's input in green/yellow color
        color = Fore.GREEN if final else Fore.YELLOW
        print(Fore.WHITE + time.strftime("%Y-%m-%d-%H:%M:%S") + " " + color, end="", flush=True)
        
        def text_stream():
            """ Stream the text from the GPT API response to console and text to speech service at the same time. """
            nonlocal response
            for processed_text in gpt_stream.text_stream:
                #processed_text = ' '.join(words_batch) + " "
                print(color + processed_text, end="", flush=True)
                response += processed_text
                yield processed_text
                time.sleep(0.25)
        
        if final:
            if not disable_voice_output:
                # In the process of speaking, do not let the user interrupt the response with new input
                audio_recorder.pause = True
                # Start the Eleven Labs text-to-speech streaming only if final response is requested
                try:
                    elevenlabs_streamer.process(voice_id, voice_model_id, text_stream())
                except ConnectionResetError:
                    print("Connection was reset by the server.")
                except Exception as e:
                    print(f"Error streaming audio: {e}")
                    if verbose:
                        print("Traceback:")
                        traceback.print_exc()
                
                audio_content = elevenlabs_streamer.get_audio_bytes()
                if audio_content:
                    save_audio_to_file(audio_content, prefix="output", extension=elevenlabs_output_format)
                else:
                    print("Could not finalize generating audio content.")
                
                elevenlabs_streamer.cleanup()
                
                # Recover the audio recorder speaking status
                audio_recorder.pause = False
            else:
                for t in gpt_stream.text_stream:
                    print(color + t, end="", flush=True)
                    response += t
            # Add the response to the messages buffer
            messages.append({
                "role": "assistant", 
                "content": [{"type": "text", "text": response.strip()}]
            })
        else:
            # Print the response to the console in real-time
            # This is the feedback response, so we won't use the text-to-speech service
            # or store the response in the messages buffer until the final response is requested
            for t in gpt_stream.text_stream:
                print(color + t, end="", flush=True)
                response += t
        
        # Increase the message word count for total GPT API usage indication
        inference_message_word_count += len(response.strip().split(" "))
        print(Fore.WHITE + f"\r\n(GPT message container word count: {inference_message_word_count})")
        if final:
            print("--------------------------------------")
        # Enable cursor blinking after the response is output
        if audio_recorder.toggle_listener:
            blink_cursor()
        # Return response for saving to log file
        return response


def gpt_inference(text, final=False):
    """
    Conducts GPT inference on the provided text prompt and logs the prompt, response, 
    and metadata to a JSON Lines file within the session directory.

    This function executes GPT inference using the `prompt` function with the given text 
    and a flag indicating whether it is a final prompt. If the inference is successful, 
    the function logs the prompt, the GPT-generated response, the current timestamp, and 
    the finality flag to a file named "inference.jsonl" in the session directory. Each 
    log entry is a single line in JSON format. In case of an error during the inference 
    process, the function prints the error message and, if debugging is enabled, the 
    traceback.

    Parameters:
    - text (str): The input text prompt for GPT inference.
    - final (bool, optional): A flag indicating whether the prompt is considered final,
                              affecting the response's mode of generation. Defaults to 
                              False.

    Global Variables:
    - audio_recorder: A global object that holds session-related information, including
                      the session directory path where logs are stored.
    - verbose (bool): A global flag indicating whether debugging information should be 
                      printed, including tracebacks on error.

    Returns:
    - bool: True if the GPT inference and logging were successful, False otherwise.

    The function attempts to perform GPT inference and log the results. On failure, it 
    catches any exceptions, optionally prints detailed error information depending on 
    the verbose flag, and returns False. On success, it returns True.
    """
    global audio_recorder, verbose
    try:
        # Perform GPT inference on the given text prompt
        response_text = prompt(text, final)
    except Exception as e:
        print(f"Error processing text; {e}")
        if verbose:
            print("Traceback:")
            traceback.print_exc()
        return False
    
    # Log the prompt, response, and metadata to a JSON Lines file
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = "inference.jsonl"
    file_path = os.path.join(audio_recorder.session_dir, filename)
    
    with open(file_path, "a") as file:
        data = {"prompt": text, "response": response_text, "timestamp": timestamp, "final": final}
        # Convert the dictionary to a JSON string and write it to the file with a newline
        json_line = json.dumps(data) + "\n"
        file.write(json_line)
    return True


def process_text(text, word_buffer):
    """
    Processes incoming text by adding its words to a buffer and performs GPT inference
    when the buffer exceeds a specified limit.

    This function is designed to accumulate text inputs into a buffer until the buffer
    reaches a predefined size limit. Once this limit is exceeded, it triggers a GPT 
    inference call with the accumulated text and then clears the buffer for new inputs. 
    This approach is useful for situations where text inputs are received piecemeal or 
    in a streaming fashion, and periodic processing is needed to generate intermediate 
    feedback or responses based on the accumulated text.

    Parameters:
    - text (str): The input text to be processed.
    - word_buffer (list): A buffer (list of words) where the words from the processed 
                          text are stored.

    Global Variables:
    - feedback_word_buffer_limit (int): The maximum number of words allowed in the 
                                        buffer before triggering GPT inference.

    The function first checks if the input text is non-empty and not just whitespace. 
    If so, it prints the text and adds its words to the word buffer. Then, it checks if 
    the updated buffer size exceeds the predefined limit. If the limit is exceeded, it 
    concatenates the buffered words into a single string and passes this string to the 
    GPT inference function, specifying that the response should be considered as 
    intermediate feedback (not final). After inference, it clears the buffer to reset 
    the process for subsequent inputs.
    """
    global feedback_word_buffer_limit
    if text.strip() != "":
        print(f"> {text}")
        word_buffer.extend(text.split(" "))
    if (len(word_buffer) + 1 > feedback_word_buffer_limit):
        # Perform GPT inference on the collected prompt,
        # but make the response an intermediate feedback only
        gpt_inference(" ".join(word_buffer), False)
        word_buffer.clear()


def save_audio_to_file(audio_data, prefix="output", extension="mp3"):
    """
    Saves the provided audio data to a file within a session-specific directory, uniquely 
    naming the file based on a prefix, a sequential number, and a specified file extension.
    
    This function examines the existing files within the session directory that match the 
    provided prefix and extension. It then determines the next available sequential number 
    to use in the filename to ensure uniqueness. The audio data is written to this newly 
    named file in binary mode.

    Parameters:
    - audio_data (bytes): The binary audio data to be saved.
    - prefix (str, optional): The prefix to be used for the filename. Defaults to "output".
    - extension (str, optional): The file extension (type) for the audio file. Defaults 
                                 to "mp3".

    Global Variables:
    - audio_recorder: A global object that contains information about the current audio 
                      session, including the directory where audio files are stored 
                      (`session_dir`).

    The function constructs the filename as follows: "{prefix}-{n}.{extension}", where 
    {n} is the next available sequential number. This file is then saved to the session 
    directory specified by `audio_recorder.session_dir`.

    No return value. The function directly writes the file to the disk.
    """
    global audio_recorder
    # List all files in the session directory
    files = os.listdir(audio_recorder.session_dir)
    
    # Filter files that start with the prefix and end with '.wav', and extract their numbers
    prefix_pattern = f"{prefix}-(\\d+)\\.{extension}"
    numbers = [int(re.search(prefix_pattern, file).group(1)) for file in files if re.match(prefix_pattern, file)]
    
    # Find the next number to use (start at 1 if no files found)
    next_nro = max(numbers) + 1 if numbers else 1
    
    filename = f"{prefix}-{next_nro}.{extension}"
    file_path = os.path.join(audio_recorder.session_dir, filename)
    
    # Save the audio data to the file
    with open(file_path, "wb") as file:
        file.write(audio_data)


###################################################
# SPEECH-TO-TEXT PROCESSING
###################################################

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
        # Process the audio data with the Google Speech Recognition API
        audio = AudioData(audio_data[0], audio_data[1], audio_data[2])
        try:
            text = recognizer.recognize_google(audio, language=language)
            if text:
                text_queue.put(text)
        except UnknownValueError:
            # Google Speech Recognition could not understand the audio
            print('?', end='\r')
        except RequestError as e:
            print(f"Could not request results from Google Speech Recognition service; {e}")
        except Exception as e:
            print(f"Error processing audio; {e}")

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
    
    def start_listening(self):
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
            if self.toggle_listener and not self.pause and not disable_voice_recognition:
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
            self.worker_process.join()
        self.active = False


###################################################
# THREADED WORKERS FOR SHORTCUT COMMANDS
###################################################

def summary_generator():
    """
    Generates a summary of the conversation from the messages stored in the chat history.

    This function processes the messages stored in the chat history, extracting the user's 
    input and the system's responses to generate a summary of the conversation. The summary 
    includes the user's prompts, the system's responses, and any additional context or 
    metadata that may be relevant for understanding the conversation flow. The function 
    constructs the summary as a formatted text block, which can be displayed to the user 
    or saved for future reference.

    Global Variables:
    - messages (list): The chat history containing messages from the user and the system.
    - summary (str): A string containing the generated summary of the conversation.

    Returns:
    - str: The summary of the conversation based on the messages in the chat history.
    """
    global messages, summary
    while True:
        # Block the thread until the keyboard shortcut is pressed
        keyboard.wait(hotkey_summarize)
        
        audio_recorder.pause = True
        freeze_cursor()
        
        # Extract the user's input and the system's responses from the messages
        previous_context = ""
        for message in messages:
            role = message["role"]
            content = message["content"]
            text = " ".join([item["text"] for item in content if item["type"] == "text"])
            if role == "user":
                previous_context += f"User: {text}\n"
            elif role == "assistant":
                previous_context += f"Assistant: {text}\n"
        
        if previous_context:
            try:
                print("Generating summary...", end="", flush=True)
                # Generate a summary prompt with the previous context
                with gpt_client.messages.stream(
                    model = gpt_model,
                    messages = [{
                        "role": "user", 
                        "content": [{"type": "text", "text": summary_generator_prompt.replace("<<summary>>", previous_context)}]
                    }],
                    max_tokens = 1024
                ) as gpt_stream:
                    # Log the prompt, response, and metadata to a JSON Lines file
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    filename = f"summary_{timestamp}.txt"
                    file_path = os.path.join(audio_recorder.session_dir, filename)
                    with open(file_path, "a") as file:
                        file.write("".join(gpt_stream.text_stream))
                    print(f" See the file: {file_path}.")
            except Exception as e:
                print(f" Error generating summary; {e}")
        else:
            print("No conversation history to summarize.")
        audio_recorder.pause = False
        blink_cursor()


def short_feedback():
    """
    Generates a short feedback response based on the user's input.

    This function processes the user's input and generates a short feedback response 
    using the GPT model. The feedback is intended to provide a quick, concise response 
    to the user's prompt, offering a brief summary or acknowledgment of the input. The 
    generated feedback is displayed to the user in the console and can be used to 
    maintain a conversational flow or provide immediate responses to user queries.

    Global Variables:
    - messages (list): The chat history containing messages from the user and the system.

    No return value. The function directly interacts with the global variable `messages` 
    to add the generated feedback response to the chat history.
    """
    global messages
    while True:
        # Block the thread until the keyboard shortcut is pressed
        keyboard.wait(hotkey_feedback)
        
        audio_recorder.pause = True
        freeze_cursor()
        
        # Extract the user's input from the messages
        user_input = ""
        for message in messages:
            if message["role"] == "user":
                user_input += " ".join([item["text"] for item in message["content"] if item["type"] == "text"])
        
        if user_input:
            # Generate a short feedback response based on the user's input
            feedback = prompt(user_input, False)
            if feedback:
                messages.append({
                    "role": "assistant", 
                    "content": [{"type": "text", "text": feedback}]
                })
        else:
            print("No user input available for feedback.")
        
        audio_recorder.pause = False
        blink_cursor()


def clear_message_history():
    """
    Clears the message history stored in the chat system.

    This function clears the message history stored in the global variable `messages`, 
    effectively resetting the conversation to an empty state. It is useful for starting 
    a new conversation or clearing the chat history to focus on a specific topic or task.

    Global Variables:
    - messages (list): The chat history containing messages from the user and the system.

    No return value. The function directly modifies the global variable `messages`.
    """
    global messages
    while True:
        # Block the thread until the keyboard shortcut is pressed
        keyboard.wait(hotkey_clear)
        
        audio_recorder.pause = True
        freeze_cursor()
        
        # Clear the message history
        messages.clear()
        print("Message history cleared.")
        
        audio_recorder.pause = False
        blink_cursor()


def activate_text_input():
    """
    Listens for a specific keyboard shortcut and, upon activation,
    prompts the user for text input to be directly processed as a prompt.
    """
    while True:
        try:
            # Block the thread until the keyboard shortcut is pressed
            keyboard.wait(hotkey_prompt)
            audio_recorder.pause = True
            freeze_cursor()
            print("\nText prompt (skip with enter):")
            user_input = input("> ").strip()
            if user_input:
                gpt_inference(user_input, final=True)
            audio_recorder.pause = False
            blink_cursor()
        except EOFError:
            break


def listen_for_flush_command():
    """
    Monitors for a specific keyboard shortcut to toggle the state of the audio 
    listener between active and paused for GPT inference processing.

    This function runs in a loop that continuously waits for the user to press 
    a combination of keys. Upon detection, it either pauses the listener if it 
    is currently active or resumes listening if it is paused. When pausing, the 
    function also triggers a GPT inference on the text collected so far, provided 
    the word buffer is not empty. After processing the collected text with GPT 
    inference, the word buffer is cleared, and the system is ready to resume 
    listening for more audio input.

    The pause state is useful for processing the accumulated audio data through 
    GPT inference without receiving more input, which might be particularly 
    beneficial in scenarios where real-time processing or batch processing of 
    spoken input is desired. Resuming the listener allows the system to start 
    capturing audio input again for subsequent processing.

    Global Variables:
    - audio_recorder: A global instance of the AudioRecorder class, which contains 
                      the current state of the listener, the word buffer for 
                      accumulating recognized text, and controls for toggling the 
                      listening state.

    This function directly interacts with the `audio_recorder` instance, using its 
    `active`, `toggle_listener`, and `word_buffer` attributes to manage the flow of 
    audio processing and GPT inference. It provides feedback to the user about the 
    current state of the listener (paused or resumed) and handles the initiation of 
    GPT inference based on the collected text.
    """
    global audio_recorder
    # Keep the thread alive while listening is active
    while audio_recorder.active:
        # Wait for the keyboard shortcut to pause/resume the listener
        keyboard.wait(hotkey_pause)
        # Toggle the listener based on the current state
        if audio_recorder.toggle_listener:
            if len(audio_recorder.word_buffer) > 0:
                if disable_voice_recognition:
                    print(Fore.RED + f"\r\nPlease wait for GPT inference. Then resume back to the input mode with {hotkey_prompt}" + Fore.WHITE)
                else:
                    print(Fore.RED + f"\r\nListener paused. Please wait for GPT inference. Then resume back to the recording mode with {hotkey_pause}." + Fore.WHITE)
                # Perform a full length GPT inference on the collected prompt
                gpt_inference(" ".join(audio_recorder.word_buffer), True)
                # Clear the word buffer after processing
                audio_recorder.word_buffer.clear()
            else:
                if disable_voice_recognition:
                    print(Fore.RED + f"No words collected for inference. Resume to input mode with {hotkey_prompt}." + Fore.WHITE)
                else:
                    print(Fore.RED + f"No words collected for inference. Resume to recording mode with {hotkey_pause}." + Fore.WHITE)
        else:
            if not disable_voice_recognition:
                print(Fore.BLUE + "Resuming listener..." + Fore.WHITE)
            blink_cursor()
            
        audio_recorder.toggle_listener = not audio_recorder.toggle_listener


def manage_word_buffer(text_queue):
    """
    Continuously retrieves recognized text from a queue and processes it for GPT 
    inference, adding each piece of text to a global word buffer managed by the 
    audio_recorder instance.

    This function runs in a loop that remains active for as long as the audio_recorder
    is set to active. It attempts to retrieve text from the provided text queue, with 
    a timeout to ensure the loop can periodically check the state of 
    `audio_recorder.active`. Upon successfully retrieving text, it calls `process_text` 
    to handle the text: printing it, adding its words to the word buffer, and 
    potentially triggering GPT inference if the buffer reaches a predefined size.

    The function plays a crucial role in the asynchronous processing of speech-to-text 
    results, facilitating real-time or near real-time processing of spoken input into 
    actionable text data for GPT inference, and ensuring the system can dynamically 
    respond to the volume of input by managing the accumulation of text in a buffer.

    Parameters:
    - text_queue (queue.Queue): The queue from which recognized text is retrieved for 
                                processing.

    Global Variables:
    - audio_recorder: A global instance of the AudioRecorder class. This function 
                      relies on the `active` flag to maintain its loop and uses the 
                      `word_buffer` attribute as a destination for processed text.

    The function ensures that even in idle times, when no text is being added to the 
    queue, it remains responsive to changes in the state of `audio_recorder.active` 
    and can exit cleanly when audio processing is concluded or when the application 
    is shutting down.
    """
    global audio_recorder
    # Keep the thread alive while listening is active
    while audio_recorder.active:
        try:
            # Get the text from the text queue and process it
            text = text_queue.get(timeout=1)
            process_text(text, audio_recorder.word_buffer)
        except Empty:
            continue


###################################################
# HELPERS FOR MAIN FUNCTION
###################################################

def import_elevenlabs_module(output_format):
    """
    Dynamically imports the appropriate ElevenlabsIO module based on the output format.
    MP3 format requires ffmpeg to be installed. WAV format is supported by default 
    Python modules. This is the reason why IO modules are separated.
    """
    if output_format == "wav":
        from .elevenlabsio import ElevenlabsIO as SelectedElevenlabsIO
    elif output_format == "mp3":
        from .elevenlabsiomp3 import ElevenlabsIO as SelectedElevenlabsIO
    else:
        raise ValueError(f"Unsupported output format: {output_format}")
    return SelectedElevenlabsIO


def validate_wav_args(sample_rate):
    """Validate WAV format arguments."""
    if sample_rate not in valid_wav_sample_rates:
        raise argparse.ArgumentTypeError(f"Invalid sample rate for WAV format. Valid options are: {valid_wav_sample_rates}")
    return sample_rate

def validate_mp3_args(bit_rate, sample_rate):
    """Validate MP3 format arguments."""
    valid_sample_rates = valid_mp3_combinations.get(bit_rate, [])
    if sample_rate not in valid_sample_rates:
        raise argparse.ArgumentTypeError(f"Invalid bit rate {bit_rate} kbps for MP3 with sample rate {sample_rate} Hz. Valid options are: {valid_mp3_combinations}")
    return bit_rate, sample_rate


def main():
    """
    Initializes and starts a bidirectional chat application with speech recognition 
    and GPT-powered responses.

    This function sets up the necessary components for a bidirectional chat application 
    where the user's speech is recognized and converted to text, processed for GPT 
    inference, and responses are generated and optionally converted to speech. It 
    parses command-line arguments to configure the application, initializes global 
    settings and resources, and manages the lifecycle of the application, including 
    starting listening for audio input, managing the word buffer, and handling user 
    commands.

    The main function handles:
    - Configuration of language settings for speech recognition.
    - Setting the feedback word buffer limit for triggering GPT inference.
    - Selection of an ElevenLabs voice ID for text-to-speech conversion.
    - Choice of a GPT model for generating text responses.
    - Enabling a verbose mode for debugging purposes.
    - Optionally listing available ElevenLabs voices and exiting.

    It uses threads to handle different parts of the application concurrently, 
    including listening for a command to flush the word buffer to GPT inference, 
    managing the word buffer, and processing text from the speech recognition queue. 
    The function ensures graceful shutdown and resource cleanup upon application 
    exit or interruption.

    Command-line arguments:
    - `-l`, `--language`: Set the language code for speech recognition.
    - `-fl`, `--feedback_limit`: Set the feedback word buffer threshold limit.
    - `-v`, `--voice_id`: Set the ElevenLabs voice ID for text-to-speech.
    - `-m`, `--gpt_model`: Select the GPT model for response generation.
    - `-u`, `--username`: Set the username for the chat.
    - `-vb`, `--verbose`: Enable verbose mode.
    - `-tl`, `--time_limit`: Set the phrase time limit for Google speech recognition.
    - `-ct`, `--calibration_time`: Set the calibration limit for Google speech recognition.
    - `-of`, `--output_audio_format`: Set the ElevenLabs output audio format (mp3 or wav).
    - `-do`, `--disable_voice_output`: Disable ElevenLabs output audio.
    - `-di`, `--disable_voice_recognition`: Disable Google voice recognition.
    - `-sf`, `--summary_file`: Import previous context for the discussion from the summary file.
    """
    global audio_recorder, feedback_word_buffer_limit, voice_id, gpt_model, username, verbose, available_models, elevenlabs_streamer, phrase_time_limit, calibration_time, elevenlabs_output_format, disable_voice_output, disable_voice_recognition, summary, summary_file, elevenlabs_output_sample_rate, elevenlabs_output_bit_rate
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Bidirectional Chat with Speech Recognition")
    
    parser.add_argument("-l", "--language", type=str, help=f"Language code for speech recognition (default: {default_input_voice_recognition_language})", default=default_input_voice_recognition_language)
    
    parser.add_argument("-fl", "--feedback_limit", type=int, help=f"feedback word buffer threshold limit to make a GPT intermediate prompt suitable for a shorter feedback (default: {feedback_word_buffer_limit})", default=feedback_word_buffer_limit)
    
    parser.add_argument("-v", "--voice_id", type=str, help=f"Elevenlabs voice id (default: {voice_id})", default=voice_id)
    
    models = ", ".join(available_models)
    parser.add_argument("-m", "--gpt_model", type=str, choices=available_models, help=f"Anthropic Claude GPT language model. Available models: {models} (default: {gpt_model})", default=gpt_model)
    
    parser.add_argument("-u", "--username", type=str, help=f"Chat username (default: {username})", default=username)
    
    parser.add_argument("-vb", "--verbose", type=bool, help=f"Verbose mode for debug purposes (default: {verbose})", default=verbose)
    
    parser.add_argument("-tl", "--time_limit", type=int, help=f"Phrase time limit for Google speech recognition (default: {phrase_time_limit})", default=phrase_time_limit)
    
    parser.add_argument("-ct", "--calibration_time", type=int, help=f"Calibration limit for Google speech recognition ambient background noise (default: {calibration_time})", default=calibration_time)
    
    parser.add_argument("-do", "--disable_voice_output", type=bool, help=f"Disable Elevenlabs output audio? (default: {disable_voice_output})", default=disable_voice_output)
    
    parser.add_argument("-di", "--disable_voice_recognition", type=bool, help=f"Disable Google voice recognition? (default: {disable_voice_recognition})", default=disable_voice_recognition)
    
    parser.add_argument("-sf", "--summary_file", type=bool, help=f"Import previous context for the discussion from the summary file (default: {summary_file})", default=summary_file)
    
    parser.add_argument("-of", "--output_audio_format", type=str, choices=["wav", "mp3"], help=f"Elevenlabs output audio format can be either mp3 or wav (default: {elevenlabs_output_format})", default=elevenlabs_output_format)
    
    parser.add_argument("-br", "--output_bit_rate", type=int, help=f"Set the output audio bitrate for Eleven Labs (default: {elevenlabs_output_bit_rate})", default=elevenlabs_output_bit_rate)
    
    parser.add_argument("-sr", "--output_sample_rate", type=int, help=f"Set the output audio samplerate for Eleven Labs MP3 stream (default: {elevenlabs_output_sample_rate})", default=elevenlabs_output_sample_rate)
    
    args = parser.parse_args()
    
    # Set the output audio format for Eleven Labs
    elevenlabs_output_format = args.output_audio_format
    
    try:
        # Additional validation for MP3 format
        if elevenlabs_output_format == "mp3":
            # Ensure the bit rate is valid for the selected sample rate
            validate_mp3_args(args.output_bit_rate, args.output_sample_rate)
        else:
            # Ensure the sample rate is valid for the WAV format
            validate_wav_args(args.output_bit_rate)
    except argparse.ArgumentTypeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Set the output audio bitrate for Eleven Labs
    # This is relevant for mp3 format only
    elevenlabs_output_sample_rate = args.output_sample_rate
    
    # Set the output audio samplerate for Eleven Labs
    elevenlabs_output_bit_rate = args.output_bit_rate
    
    # Import the correct ElevenlabsIO module based on the command line format argument
    ElevenlabsIO = import_elevenlabs_module(elevenlabs_output_format)
    
    # Initialize the Eleven Labs streamer
    if elevenlabs_output_format == "wav":
        # For WAV format, only the bit rate is needed
        kwargs = {"bit_rate": elevenlabs_output_bit_rate}
    else:
        # For MP3 format, both the sample rate and bit rate are needed
        kwargs = {"sample_rate": elevenlabs_output_sample_rate, "bit_rate": elevenlabs_output_bit_rate}
    
    # Initialize the Eleven Labs streamer with the appropriate arguments
    elevenlabs_streamer = ElevenlabsIO(**kwargs)
    
    # Set the word buffer limit
    feedback_word_buffer_limit = args.feedback_limit
    
    # Set the Anthropic Claude GPT model
    gpt_model = args.gpt_model
    
    # Set the Eleven Labs voice ID
    voice_id = args.voice_id
    
    # Verbose print debug
    verbose = args.verbose
    
    # Disable Elevenlabs voice output
    disable_voice_output = args.disable_voice_output
    
    # Disable Google voice recognition
    disable_voice_recognition = args.disable_voice_recognition
    
    # Set chat username
    username = args.username
    
    # Set the Google speech recognition phrase time limit
    phrase_time_limit = args.time_limit
    
    # Set the Google speech recognition background ambient noise calibration time
    calibration_time = args.calibration_time
    
    # If summary file is provided and exists, read the summary from the file
    if args.summary_file:
        summary_file = args.summary_file
        if os.path.exists(summary_file):
            with open(summary_file, "r") as file:
                summary = file.read()
        else:
            print(f"Summary file ({summary_file}) does not exist.")
    
    # Initialize the AudioRecorder class
    audio_recorder = AudioRecorder(language=args.language)
    
    # ANSI escape codes for screen clear and cursor home
    print(chr(27) + "[2J" + chr(27) + "[;H")
    print(ascii_art)
    print("############################################################")
    
    if not disable_voice_recognition:
        audio_recorder.start_listening()
    
    # Print the hotkeys for user interaction
    print(f"# To get a full response, press {invert_text(hotkey_pause)}.\n# You can also enter text commands using {invert_text(hotkey_prompt)}.\n# To summarize dialogue, use {invert_text(hotkey_summarize)}.\n# Clear message history: {invert_text(hotkey_clear)}. Exit the bot: {invert_text(hotkey_exit)}.")
    print("############################################################\n")

    blink_cursor()
    
    # Start the flush command listener thread
    flush_thread = Thread(target=listen_for_flush_command)
    flush_thread.daemon = True
    flush_thread.start()
    
    # Create a thread targeting the activate_text_input function
    input_thread = Thread(target=activate_text_input)
    input_thread.daemon = True
    input_thread.start()
    
    # Create a thread targeting the activate_text_input function
    summary_thread = Thread(target=summary_generator)
    summary_thread.daemon = True
    summary_thread.start()
    
    # Clear message history
    clear_history_thread = Thread(target=clear_message_history)
    clear_history_thread.daemon = True
    clear_history_thread.start()
    
    # Clear message history
    short_feedback_thread = Thread(target=short_feedback)
    short_feedback_thread.daemon = True
    short_feedback_thread.start()

    # Start the word buffer manager thread
    buffer_manager_thread = Thread(target=manage_word_buffer, args=(audio_recorder.text_queue,))
    buffer_manager_thread.daemon = True
    buffer_manager_thread.start()

    try:
        # Keep the main thread alive
        while audio_recorder.active:
            time.sleep(1)
    except KeyboardInterrupt:
        # Exit the program on keyboard interrupt
        audio_recorder.active = False
    finally:
        # Cleanup the resources and exit the program
        elevenlabs_streamer.quit()
        audio_recorder.cleanup()
        freeze_cursor()
        print(Fore.WHITE + "Program exited.\n")


if __name__ == "__main__":
    """ Entry point for the script. """
    main()

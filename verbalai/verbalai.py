# verbalai.py - A Python script for near real-time voice-to-text, text to prompt text and text-to-speech interaction with an AI chatbot.
# Native library imports
import os
import re
import sys
import time
import json
import argparse
import traceback
import subprocess
from queue import Empty
from threading import Thread
from contextlib import contextmanager
# Installed packages
import keyboard
from anthropic import Anthropic
from openai import OpenAI
from colorama import init, Fore, Style, Back
# Library imports
from .prompts import (
    short_mode,
    long_mode,
    previous_context,
    system_message,
    system_message_tools,
    summary_generator_prompt,
    system_message_metadata,
    system_message_find_database,
    system_message_find_database_entry,
    system_message_database_statistic,
    system_message_tools_human_format,
    system_message_metadata_without_tools
)
from .audio_stream_server import ServerThread
from .deepgramio import DeepgramIO
from .VectorDB import VectorDB
# NOTE: tool chain and intent module has been disabled
# these and associated variables can be uncommented,
# if developing the sub project related to them
# at the moment, custom model and claude tool inference does not
# work seamlessly in the user/AI dialogue compared to
# providing tools in system prompt as json schemas
#from .commands import predict_intent
#from .tool_chain import ToolChain
from .gpt_token_calculator import GPTTokenCalculator

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

# Initialize the VectorDB instance
vector_db = VectorDB()

# Initialize the ToolChain instance
#tool_chain = None

# Initialize the intent (command) model path
intent_model_path = "models/vai_model"

# Initialize the low confidence threshold for command model tool prediction
low_confidence_threshold = 0.899

# Initialize session id
session_id = None

# Global variables
default_input_voice_recognition_language = "en-US"
feedback_word_buffer_limit = 25
feedback_token_limit = 20
response_token_limit = 150
# For testing purposes, set the phrase time limit to 5 seconds
feedback_word_buffer_limit = 25
feedback_token_limit = 20
response_token_limit = 250

# Google speech recognition properties
phrase_time_limit = 10
calibration_time = 2

# Debug mode flag
verbose = False

# Anthropic Claude GPT model
gpt_model = "claude-3-haiku-20240307"

# Available Anthropic Claude and OpenAI GPT models
anthropic_models = [
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307"
]

openai_models = [
    "gpt-4-turbo-2024-04-09",
    "gpt-4-0125-preview",
    "gpt-4-1106-preview",
    "gpt-4-32k-0314",
    "gpt-4-turbo",
    "gpt-4-0314",
    "gpt-4-32k",
    "gpt-4",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-0301",
    "gpt-3.5-turbo-16k-0613"
]

# Flag to indicate whether to use function calling tools or not
use_function_calling_tools = False

# Command extraction model
command_extraction_model = "claude-3-haiku-20240307"

# Available models for the chatbot
available_models = anthropic_models + openai_models

# Eleven Labs voice ID: Male voice (Drew)
voice_id = "29vD33N1CtxCmqQRPOHJ"

# Deepgram voice ID
deepgram_voice_id = "aura-asteria-en"

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

# Initialize the GPT clients
# Note: dotenv handles the API key loading
# Initialize the Anthropic client
gpt_client = Anthropic()

# Initialize the OpenAI client
gpt_client_openai = OpenAI()

# Initialize the session message buffer
messages = []

# Initialize the meessage counter for monitoring the API request usage
inference_message_word_count = 0

# Audio recorder type for voice recognition: GoogleSpeech or Deepgram
audio_recorder_type = "GoogleSpeech"

# Keyboard shortcuts for controlling the chatbot
hotkey_pause     = "ctrl+alt+p" # Toggle response mode
hotkey_prompt    = "ctrl+alt+t" # Text prompt for the GPT model
hotkey_clear     = "ctrl+alt+c" # Clear the chat history
hotkey_feedback  = "ctrl+alt+f" # Activate short feedback
hotkey_summarize = "ctrl+alt+s" # Generate a summary of the conversation
hotkey_exit      = "ctrl+c"     # Exit the chatbot

# Summary and previous context summary file
summary, summary_file = "", ""

# Audio file source for voice recognition
# Either local file or url (wav / mp3)
audio_file_source = ""

# Audio file server settings
audio_dir = "audio_files"
audio_host = "127.0.0.1"
audio_port = 5000
audio_stream = False

deepgram_streamer = None

use_deepgram_streamer = False

gpt_token_calculator = None

###################################################
# CONSOLE MAGIC
###################################################

def blink_cursor():
    """ Blinks the cursor to indicate that the system is waiting for user input. """
    sys.stdout.write('\033[?12h')
    sys.stdout.flush()


def freeze_cursor():
    """ Freezes the cursor to prevent user input during system output. """
    sys.stdout.write('\033[?12l')
    sys.stdout.flush()


def invert_text(text):
    """ Inverts the text color and background color for a given text string. """
    return Back.RED + Style.BRIGHT + Fore.BLACK + text + Style.RESET_ALL


###################################################
# COGNITIVE MODEL CALLBACKS
###################################################


def find_discussions(kwargs):
    try:
        discussions = vector_db.find_discussions(**kwargs)
        return f"\n\n{[{'discussion_id': value['discussion_id'], 'starttime': value['starttime'], 'title': value['title'], 'categories': ', '.join([category['name'] for category in value['categories']])} for id in discussions for value in [vector_db.retrieve_discussion_by_id(id)] if 'categories' in value]}", True
    except Exception as e:
        return f"There was a problem on finding the discussions; {e}", False


def find_dialogue_units(kwargs):
    try:
        dialogues, distances = vector_db.find_dialogue_units(**kwargs)
        return f"\n\n{[{key: (value[:40] + ('...' if len(value) > 40 else '')) if key in ['prompt', 'response'] else value for key, value in vector_db.retrieve_dialogue_unit_by_id(id).items() if key in ['dialogue_unit_id', 'timestamp', 'prompt', 'response']} for id in dialogues]}. Format in markdown table format starting with id.", True
    except Exception as e:
        return f"There was a problem on finding the dialogue units; {e}", False


def retrieve_discussion_by_id(kwargs):
    try:
        kwargs["discussion_id"] = vector_db.extract_discussion_id(kwargs["discussion_id"], include_random=True)
        discussion = vector_db.retrieve_discussion_by_id(kwargs["discussion_id"])
        return f"Discussion details: {discussion}", True
    except Exception as e:
        return f"There was a problem on retrieving the discussion; {e}", False


def retrieve_dialogue_unit_by_id(kwargs):
    try:
        dialogue = vector_db.retrieve_dialogue_unit_by_id(kwargs["dialogue_unit_id"])
        return f"Dialogue unit details: {dialogue}", True
    except Exception as e:
        return f"There was a problem on retrieving the dialogue unit; {e}", False


def remove_category(kwargs):
    try:
        kwargs["discussion_id"] = vector_db.extract_discussion_id(kwargs["discussion_id"])
        vector_db.remove_category(**kwargs)
        categories = vector_db.retrieve_categories(kwargs["discussion_id"])
        return f"Discussion category has been removed successfully. Categories for the modified discussion are currently: {categories}", True
    except Exception as e:
        return f"There was a problem on removing the category from the discussion; {e}", False


def modify_discussion(kwargs):
    try:
        kwargs["discussion_id"] = vector_db.extract_discussion_id(kwargs["discussion_id"])
        vector_db.modify_discussion(**kwargs)
        discussion = vector_db.retrieve_discussion_by_id(kwargs["discussion_id"])
        return f"Discussion name|featured flag has been modified successfully. Discussion details are currently: {discussion}", True
    except Exception as e:
        return f"There was a problem on modifying the discussion; {e}", False


def assign_category(kwargs):
    try:
        kwargs["discussion_id"] = vector_db.extract_discussion_id(kwargs["discussion_id"])
        vector_db.assign_category(**kwargs)
        categories = vector_db.retrieve_categories(kwargs["discussion_id"])
        return f"Category has been assigned to the discussion successfully. Categories for the modified discussion are currently: {categories}", True
    except Exception as e:
        return f"There was a problem on assigning category to the discussion; {e}", False


callbacks = {
    "assign_category": lambda kwargs: assign_category(kwargs),
    "modify_discussion": lambda kwargs: modify_discussion(kwargs),
    "remove_category": lambda kwargs: remove_category(kwargs),
    "retrieve_dialogue_unit_by_id": lambda kwargs: retrieve_dialogue_unit_by_id(kwargs),
    "retrieve_discussion_by_id": lambda kwargs: retrieve_discussion_by_id(kwargs),
    "find_discussions": lambda kwargs: find_discussions(kwargs),
    "find_dialogue_units": lambda kwargs: find_dialogue_units(kwargs)
}


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
    
    global gpt_token_calculator, inference_message_word_count, gpt_model, system_message, system_message_tools, messages, short_mode, long_mode, username, response_token_limit, feedback_token_limit, voice_model_id, elevenlabs_streamer, disable_voice_output, verbose, deepgram_streamer, deepgram_voice_id, system_message_find_database, system_message_find_database_entry, system_message_database_statistic, command_extraction_model, tool_chain, low_confidence_threshold, intent_model_path, use_function_calling_tools, system_message_tools_human_format
    
    text = text.strip()
    
    inference_message_word_count += len(text.split(" "))
    
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"].append({"type": "text", "text": text})
    else:
        messages.append({
            "role": "user", 
            "content": [{"type": "text", "text": text}]
        })
    
    topics = []
    sentiment = {}
    intent = ""
    tools = []
    
    # Retrieve user prompt metadata and function calling tool extraction with GPT
    # Metadata function relies on the global messages variable
    latest_messages = messages[-5:]
    metadata = gpt_retrieve_metadata(latest_messages)
    if metadata:
        topics = metadata.get("topics", [])
        sentiment = metadata.get("sentiment", {})
        intent = metadata.get("intent", "")
        tools = metadata.get("tools", [])
    
    logger.info(metadata)

    if final and use_function_calling_tools and tools:
        
        # If tools are found, use them to infer extra content to the messages
        
        # TODO: At the moment, consequencing tools do not known the results provided
        # by the earlier tool. That could be achieved by including metadata retrieval to the loop
        # and let LLM construct arguments again. If messages contain the former results, LLM could
        # possibly infer the correct arguments based on the last result. But on the other hand,
        # for efficiency, there can be cases where former results has no effect of the latter
        # tools. Also, intent, sentiment, and topics are redundant in the latter tools so the 
        # metadata retrieval system prompt might benefit on being different compared to the initial one
        print("")
        for entry in tools:
            
            tool, args = entry["tool"], entry["arguments"]
            
            success = False
            response = ""
            tool_messages = []
            predicted_tool = tool
            
            if predicted_tool in callbacks:
                try:
                    # Call the callback function for the tool
                    tool_answer, success = callbacks[predicted_tool](args)
                    
                    logger.info(f"Tool '{predicted_tool}' response ({success}): '{tool_answer}'.")
                    
                    assistant_message = f"Calling tool: {predicted_tool}. Input: {args}"
                    user_message = f"User role: tool. Output: {tool_answer}"
                    # Note: Tool schema words count is not included
                    inference_message_word_count += len(assistant_message.split(" "))
                    inference_message_word_count += len(user_message.split(" "))
                    
                    tool_messages = [
                        {"role": "assistant", "content": [
                                {"type": "text", "text": assistant_message}
                            ]
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_message}
                            ]
                        }
                    ]
                    
                    if success:
                        print(f"{Fore.YELLOW}✓ Tool {predicted_tool} activated and request succeed.\n")
                    else:
                        response = f"Error executing tool: {predicted_tool}; {tool_answer}"
                        print(f"{Fore.RED}✗ {response}\n")
                    
                    intent = predicted_tool
                    
                except Exception as e:
                    response = f"Error executing tool: {predicted_tool}; {e}"
                    print(f"\n{Fore.RED}✗ {response}\n")
                
            else:
                print(f"\n{Fore.YELLOW}? Tool not found: {predicted_tool}\n")
            
            # If tool processing succeeded, add the tool messages
            if tool_messages:
                messages.extend(tool_messages)
            # else, add error response to messages
            elif response:
                messages.extend([
                    {
                        "role": "assistant", 
                        "content": [{"type": "text", "text": "Processing the tool function request..."}]
                    },
                    {
                        "role": "user", 
                        "content": [{"type": "text", "text": f"User role: tool. Output: {response}"}]
                    }
                ])
    
    # Generate the system message with the current mode, username, datetime, and previous context
    system = system_message.\
        replace("<<mode>>", long_mode if final else short_mode).\
        replace("<<tools>>", system_message_tools_human_format if use_function_calling_tools else "").\
        replace("<<user>>", username).\
        replace("<<datetime>>", time.strftime("%Y-%m-%d %H:%M:%S")).\
        replace("<<previous_context>>", previous_context.\
            replace("<<summary>>", summary) if summary else "").\
        replace("<<discussion_id>>", str(vector_db.current_discussion_id)).\
        replace("<<previous_discussion>>", str(vector_db.previous_discussion)).\
        replace("<<first_discussion_date>>", vector_db.first_discussion_date)
    
    # Log last 5 messages without index error
    logger.info(messages[-min(len(messages), 5):])
    
    start_time = None
    @contextmanager
    def get_gpt_stream():
        """ Get the GPT API stream for generating responses. """
        nonlocal start_time
        try:
            logger.info(f"Open GPT text stream. Start timer.")
            start_time = time.time()
            # Check if the GPT model is an Anthropic model
            if gpt_model in anthropic_models:
                with gpt_client.messages.stream(
                    model = gpt_model,
                    messages = messages,
                    max_tokens = response_token_limit if final else feedback_token_limit,
                    system = system + (" - Answer shortly by few words only." if not final else "")
                ) as stream:
                    yield stream.text_stream
                    gpt_token_calculator.update_token_counts(stream.get_final_message(), gpt_model)
            # Else assume OpenAI model
            else:
                def openai_stream():
                    chat_messages = [{"role": "system", "content": system + (" - Answer shortly by few words only." if not final else "")}] + messages
                    chunks = gpt_client_openai.chat.completions.create(
                        model = gpt_model,
                        messages = chat_messages,
                        max_tokens = response_token_limit if final else feedback_token_limit,
                        stream = True,
                    )
                    for chunk in chunks:
                        if chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content
                    
                    # TODO: collect contents from chat_messages
                    # gpt_token_calculator.update_token_counts(chunks, gpt_model, chat_messages)
                # Yield the generator itself for with context
                yield openai_stream()
                
        except Exception as e:
            logger.error(f"Error getting GPT stream: {e}")
            raise
    
    streamer = elevenlabs_streamer if elevenlabs_streamer else deepgram_streamer
    
    with get_gpt_stream() as gpt_stream:

        response = ""
        
        # Freezed cursor indicates that system is outputting, not waiting for an input
        freeze_cursor()
        
        # Print the current time and the user's input in green/yellow color
        color = Fore.GREEN if final else Fore.YELLOW
        print(Fore.WHITE + time.strftime("%Y-%m-%dT%H:%M:%S") + " " + color, end="", flush=True)
        
        def text_stream():
            """ Stream the text from the GPT API response to console and text to speech service at the same time. """
            nonlocal response
            for processed_text in gpt_stream:
                print(color + processed_text, end="", flush=True)
                response += processed_text
                yield processed_text
                #time.sleep(0.25)
        
        if final:
            if not disable_voice_output:
                # In the process of speaking, do not let the user interrupt the response with new input
                audio_recorder.pause = True
                # Start the Eleven Labs text-to-speech streaming only if final response is requested
                try:
                    streamer.process(deepgram_voice_id if deepgram_streamer else voice_id, voice_model_id, text_stream, start_time)
                except ConnectionResetError:
                    logger.error("Connection was reset by the server.")
                except Exception as e:
                    logger.error(f"Error streaming audio: {e}")
                    if verbose:
                        traceback.print_exc()
                
                audio_content = streamer.get_audio_bytes()
                if audio_content:
                    save_audio_to_file(audio_content, prefix="output", extension=elevenlabs_output_format)
                else:
                    logger.error("Could not finalize generating audio content.")
                
                streamer.cleanup()
                
                # Recover the audio recorder speaking status
                audio_recorder.pause = False
            else:
                for t in gpt_stream:
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
            for t in gpt_stream:
                print(color + t, end="", flush=True)
                response += t
        
        # Increase the message word count for total GPT API usage indication
        inference_message_word_count += len(response.strip().split(" "))
        print(Fore.WHITE + f" ({inference_message_word_count}/${gpt_token_calculator.get_cost()})")
        # Return response for saving to log file
        return response, topics, sentiment, intent


def gpt_retrieve_content(messages, system_message, max_tokens = 100, model = None):
    
    global gpt_model, anthropic_models, gpt_client_openai, gpt_client, gpt_token_calculator
    
    result = None
    
    model = model if model else gpt_model
    
    if gpt_model in anthropic_models:
        message = gpt_client.messages.create(
            model = model,
            messages = messages,
            max_tokens = max_tokens,
            system = system_message,
            temperature = 0
        )
        result = message.content[0].text
        gpt_token_calculator.update_token_counts(message, model)
    # Else assume OpenAI model
    else:
        chat_messages = [
            {"role": "system", "content": system_message},
        ] + messages
        message = gpt_client_openai.chat.completions.create(
            model = model,
            messages = chat_messages,
            max_tokens = max_tokens,
            temperature = 0
        )
        result = message.choices[0].message.content
        gpt_token_calculator.update_token_counts(message, model, result)
    return result

# TODO: remove
def loads_first_json_block(text):
    # Initial counts and flags
    brace_count = 0
    in_string = False
    escape = False
    json_start = -1
    json_end = -1

    # Iterate over the text by index and character
    for i, char in enumerate(text):
        if char == '"' and not escape:
            in_string = not in_string
        elif char == '\\' and not escape:
            escape = True
            continue
        elif char == '{' and not in_string:
            if brace_count == 0:
                json_start = i
            brace_count += 1
        elif char == '}' and not in_string:
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break
        escape = False

    logger.info(f"Retrieved JSON block: {text}")
    # Extract and parse the JSON string if braces match up
    if json_start != -1 and json_end != -1:
        json_string = text[json_start:json_end]
        try:
            logger.info(f"Extracted JSON: {json_string}")
            return json.loads(json_string)
        except Exception as e:
            logger.error(f"Error extracting JSON: {e}")
    else:
        logger.warn("No JSON string found.")
    
    return {}


def extract_and_parse_json_block(text):
    results = []
    # Regex to extract all {} enclosed blocks, handling nested structures
    pattern = re.compile(r'\{(?:[^{}]*(?:\{(?:[^{}]*(?:\{[^{}]*\})*[^{}]*)*\})*[^{}]*)*\}')
    blocks = pattern.findall(text)
    for block in blocks:
        try:
            # Attempt to load the JSON block
            parsed_json = json.loads(block)
            # Check for required keys in the JSON
            if all(map(lambda x: x in parsed_json, ['topics', 'sentiment', 'intent', 'tools'])):
                results.append(parsed_json)
        except json.JSONDecodeError:
            # If decoding fails, skip this block
            continue
    return results[0] if len(results) == 1 else {}


def gpt_retrieve_metadata(messages):
    
    global system_message_metadata, command_extraction_model, username, system_message_tools, use_function_calling_tools, system_message_metadata_without_tools
    
    result = gpt_retrieve_content(
        messages, 
        (system_message_metadata if use_function_calling_tools else system_message_metadata_without_tools).\
            replace("<<tools>>", system_message_tools if use_function_calling_tools else "").\
            replace("<<user>>", username).\
            replace("<<datetime>>", time.strftime("%Y-%m-%d %H:%M:%S")).\
            replace("<<discussion_id>>", str(vector_db.current_discussion_id)).\
            replace("<<previous_discussion>>", str(vector_db.previous_discussion)).\
            replace("<<first_discussion_date>>", vector_db.first_discussion_date), 
        500,
        # Claude 3 Sonnet LLM seems to work best with prompt with schema to arguments inference,
        # but Haiku is much cheaper and works almost as well.
        command_extraction_model
    )
    
    return extract_and_parse_json_block(result) if result else {}


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
    global verbose, vector_db
    try:
        # Perform GPT inference on the given text prompt
        response_text, topics, sentiment, intent = prompt(text, final)
    except Exception as e:
        logger.error(f"Error on processing text; {e}")
        print(f"Error on processing text; {e}")
        if verbose:
            traceback.print_exc()
        return False
        
    vector_db.add_dialogue_unit(
        text, 
        response_text, 
        topics, 
        sentiment, 
        intent
    )

    # Log the prompt, response, and metadata to a JSON Lines file
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = "inference.jsonl"
    file_path = os.path.join(audio_recorder.session_dir, filename)
    
    with open(file_path, "a") as file:
        data = {
            "prompt": text, 
            "response": response_text, 
            "topics": topics, 
            "sentiment": sentiment, 
            "intent": intent, 
            "timestamp": timestamp, 
            "final": final
        }
        # Convert the dictionary to a JSON string and write it to the file with a newline
        json_line = json.dumps(data) + "\n"
        file.write(json_line)
    return True


def process_text(text, word_buffer, print_buffer):
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
    global feedback_word_buffer_limit, audio_recorder
    if text.strip() != "":
        if audio_recorder.pause:
            print_buffer.extend(text)
        else:
            if print_buffer:
                for print_text in print_buffer:
                    print(f"> {print_text}")
                print_buffer.clear()
            print(f"> {text}")
        word_buffer.extend(text.split(" "))
    if ((len(word_buffer) + 1) > feedback_word_buffer_limit) and not audio_recorder.pause:
        # Perform GPT inference on the collected prompt,
        # but make the response an intermediate feedback only
        text = " ".join(word_buffer)
        word_buffer.clear()
        gpt_inference(text, final=False)
        blink_cursor()


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
                        summary = "".join(gpt_stream.text_stream)
                        file.write(summary)
                        vector_db.add_dialogue_unit(
                            summary, 
                            "", 
                            ["summary"]
                        )
                    print(f" See the file: {file_path}.")
            except Exception as e:
                logger.error(f" Error generating summary; {e}")
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
            response_text, topics, sentiment, intent = prompt(user_input, False)
            if response_text:
                messages.append({
                    "role": "assistant", 
                    "content": [{"type": "text", "text": response_text}]
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
                    print(Fore.RED + f"\r\nPlease wait for GPT inference." + Fore.WHITE)
                else:
                    print(Fore.RED + f"\r\nListener paused. Please wait for GPT inference." + Fore.WHITE)
                # Perform a full length GPT inference on the collected prompt
                prompt = " ".join(audio_recorder.word_buffer)
                audio_recorder.word_buffer.clear()
                gpt_inference(prompt, final=True)
                # Provide feedback to user to resume the recording mode
                print(Fore.RED + f"Resume back to the recording mode with {hotkey_pause}." + Fore.WHITE)
                # Clear the word buffer after processing
                #audio_recorder.word_buffer.clear()
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
            process_text(text, audio_recorder.word_buffer, audio_recorder.print_buffer)
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
        if not is_ffmpeg_installed():
            raise ImportError("ffmpeg is required for MP3 processing but not found. Download from: https://ffmpeg.org/")
    else:
        raise ValueError(f"Unsupported output format: {output_format}")
    return SelectedElevenlabsIO


def import_audiorecorder_module(recorder_type):
    """
    Dynamically imports the appropriate ElevenlabsIO module based on the output format.
    MP3 format requires ffmpeg to be installed. WAV format is supported by default 
    Python modules. This is the reason why IO modules are separated.
    """
    if recorder_type == "GoogleSpeech":
        from .GoogleSpeechAudioRecorder import AudioRecorder
    elif recorder_type == "Deepgram":
        from .DeepgramAudioRecorder import AudioRecorder
        if not is_ffmpeg_installed():
            raise ImportError("ffmpeg is required for MP3 processing but not found. Download from: https://ffmpeg.org/")
    else:
        raise ValueError(f"Unsupported output format: {recorder_type}")
    return AudioRecorder


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
    - `-do`, `--disable_voice_output`: Disable output audio.
    - `-di`, `--disable_voice_recognition`: Disable voice recognition.
    - `-sf`, `--summary_file`: Import previous context for the discussion from the summary file.
    """
    global gpt_token_calculator, audio_recorder, feedback_word_buffer_limit, voice_id, gpt_model, username, verbose, available_models, elevenlabs_streamer, phrase_time_limit, calibration_time, elevenlabs_output_format, disable_voice_output, disable_voice_recognition, summary, summary_file, elevenlabs_output_sample_rate, elevenlabs_output_bit_rate, audio_file_source, audio_recorder_type, audio_dir, audio_host, audio_port, audio_stream, deepgram_streamer, use_deepgram_streamer, session_id, tool_chain, intent_model_path, low_confidence_threshold, use_function_calling_tools, deepgram_voice_id
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Bidirectional Chat with Speech Recognition")
    
    parser.add_argument("-l", "--language", type=str, help=f"Language code for speech recognition (default: {default_input_voice_recognition_language})", default=default_input_voice_recognition_language)
    
    parser.add_argument("-fl", "--feedback_limit", type=int, help=f"feedback word buffer threshold limit to make a GPT intermediate prompt suitable for a shorter feedback (default: {feedback_word_buffer_limit})", default=feedback_word_buffer_limit)
    
    parser.add_argument("-v", "--voice_id", type=str, help=f"Elevenlabs voice id (default: {voice_id})", default=voice_id)
    
    parser.add_argument("-dv", "--deepgram_voice_id", type=str, help=f"Deepgram voice id (default: {deepgram_voice_id})", default=deepgram_voice_id)
    
    models = ", ".join(available_models)
    parser.add_argument("-m", "--gpt_model", type=str, help=f"Anthropic Claude / OpenAI GPT language model. Available models: {models} (default: {gpt_model})", default=gpt_model)
    
    parser.add_argument("-u", "--username", type=str, help=f"Chat username (default: {username})", default=username)
    
    parser.add_argument("-vb", "--verbose", action=('store_false' if verbose else 'store_true'), help=f"Verbose mode for debug purposes (default: {verbose})")
    
    parser.add_argument("-tl", "--time_limit", type=int, help=f"Phrase time limit for Google speech recognition (default: {phrase_time_limit})", default=phrase_time_limit)
    
    parser.add_argument("-ct", "--calibration_time", type=int, help=f"Calibration limit for Google speech recognition ambient background noise (default: {calibration_time})", default=calibration_time)
    
    parser.add_argument("-do", "--disable_voice_output", action=('store_false' if disable_voice_output else 'store_true'), help=f"Disable output audio? (default: {disable_voice_output})")
    
    parser.add_argument("-di", "--disable_voice_recognition", action=('store_false' if disable_voice_recognition else 'store_true'), help=f"Disable voice recognition? (default: {disable_voice_recognition})")
    
    parser.add_argument("-sf", "--summary_file", type=str, help=f"Import previous context for the discussion from the summary file (default: {summary_file})", default=summary_file)
    
    parser.add_argument("-s", "--summary", type=str, help=f"Provide previous context for the discussion from the text summary (default: {summary})", default=summary)
    
    parser.add_argument("-of", "--output_audio_format", type=str, choices=["wav", "mp3"], help=f"Elevenlabs output audio format can be either mp3 or wav (default: {elevenlabs_output_format})", default=elevenlabs_output_format)
    
    parser.add_argument("-br", "--output_bit_rate", type=int, help=f"Set the output audio bitrate for Eleven Labs (default: {elevenlabs_output_bit_rate})", default=elevenlabs_output_bit_rate)
    
    parser.add_argument("-sr", "--output_sample_rate", type=int, help=f"Set the output audio samplerate for Eleven Labs MP3 stream (default: {elevenlabs_output_sample_rate})", default=elevenlabs_output_sample_rate)
    
    parser.add_argument("-fs", "--file_source", type=str, help=f" (default: {audio_file_source})", default=audio_file_source)
    
    parser.add_argument("-at", "--audio_recorder_type", type=str, choices=["GoogleSpeech", "Deepgram"], help=f" (default: {audio_recorder_type})", default=audio_recorder_type)
    
    parser.add_argument("-ah", "--audio_host", type=str, help=f"Audio host for streaming files (default: {audio_host})", default=audio_host)
    
    parser.add_argument("-ap", "--audio_port", type=int, help=f"Audio host port for streaming files (default: {audio_port})", default=audio_port)
    
    parser.add_argument("-ad", "--audio_dir", type=str, help=f"Audio directory for streaming files (default: {audio_dir})", default=audio_dir)
    
    parser.add_argument("-as", "--audio_stream", action=('store_false' if audio_stream else 'store_true'), help=f"Should we stream source audio files? (default: {audio_stream})")
    
    parser.add_argument("-dg", "--use_deepgram_streamer", action=('store_false' if use_deepgram_streamer else 'store_true'), help=f"Should we use deepgram for streaming text to voice? (default: {use_deepgram_streamer})")
    
    parser.add_argument("-im", "--intent_model_path", type=str, default=intent_model_path, help="Path to the intent prediction model.")
    
    parser.add_argument("-lct", "--low_confidence_threshold", type=float, default=low_confidence_threshold, help="Threshold below which predictions are considered to have low confidence and are not executed in the command model.")
    
    parser.add_argument("-fct", "--use_function_calling_tools", action=('store_false' if use_function_calling_tools else 'store_true'), help=f"Should we use function calling tools? (default: {use_function_calling_tools})")
    
    args = parser.parse_args()
    
    if args.gpt_model not in available_models:
        parser.error(f"The specified model is not supported. Please choose from the following models: {models}")
    
    if audio_dir and not os.path.exists(audio_dir):
        os.makedirs(audio_dir, exist_ok=True)
            
    logger.info("Program started.")
        
    if args.use_deepgram_streamer:
        # Initialize the Deepgram streamer
        deepgram_streamer = DeepgramIO()
    else:
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
        
        initial_buffer_size = 2
        # Initialize the Eleven Labs streamer
        if elevenlabs_output_format == "wav":
            # For WAV format, only the bit rate is needed
            kwargs = {"bit_rate": elevenlabs_output_bit_rate, "audio_buffer_in_seconds": initial_buffer_size}
        else:
            # For MP3 format, both the sample rate and bit rate are needed
            kwargs = {"sample_rate": elevenlabs_output_sample_rate, "bit_rate": elevenlabs_output_bit_rate, "audio_buffer_in_seconds": initial_buffer_size}
        
        # Initialize the Eleven Labs streamer with the appropriate arguments
        elevenlabs_streamer = ElevenlabsIO(**kwargs)
    
    # Set the word buffer limit
    feedback_word_buffer_limit = args.feedback_limit
    
    # Set the Anthropic Claude GPT model
    gpt_model = args.gpt_model
    
    # Initialize function calling tools
    use_function_calling_tools = args.use_function_calling_tools
    
    # Initialize the tool chain with the selected GPT model
    #tool_chain = ToolChain(model=gpt_model)
    
    # Set intent (command) model path
    intent_model_path = args.intent_model_path
    
    # Set the low confidence threshold for the command model
    low_confidence_threshold = args.low_confidence_threshold
    
    # 
    gpt_token_calculator = GPTTokenCalculator()
    
    # Set the Eleven Labs voice ID
    voice_id = args.voice_id
    
    # Set the Deepgram voice ID
    deepgram_voice_id = args.deepgram_voice_id
    
    # Verbose print debug
    verbose = args.verbose
    
    # Determine the logging level based on the verbose argument
    if verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    
    # Only set up logging if no handlers are configured yet
    if not logging.getLogger().hasHandlers():
        setup_logging(log_level)
    
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
    
    # Set previous conversation summary
    if args.summary:
        summary = args.summary
    
    # Use the provided audio file source for recognition
    audio_file_source = args.file_source
    
    # Set the audio recorder type
    audio_recorder_type = args.audio_recorder_type
    
    # Import the correct audio recorder module based on the command line recorder type argument
    audio_recorder_class = import_audiorecorder_module(audio_recorder_type)
    
    # Initialize the AudioRecorder instance
    audio_recorder = audio_recorder_class(language=args.language)
    
    # Initialize session id for the application via VectorDB class
    session_id = vector_db.create_new_session()

    # Start the flush command listener thread
    flush_thread = Thread(target=listen_for_flush_command, daemon=True)
    flush_thread.start()
    
    # Create a thread targeting the activate_text_input function
    input_thread = Thread(target=activate_text_input, daemon=True)
    input_thread.start()
    
    # Create a thread targeting the activate_text_input function
    summary_thread = Thread(target=summary_generator, daemon=True)
    summary_thread.start()
    
    # Clear message history
    clear_history_thread = Thread(target=clear_message_history, daemon=True)
    clear_history_thread.start()
    
    # Short feedback
    #short_feedback_thread = Thread(target=short_feedback, daemon=True)
    #short_feedback_thread.start()
    
    # Start the word buffer manager thread
    buffer_manager_thread = Thread(
        target=manage_word_buffer, 
        args=(audio_recorder.text_queue,), 
        daemon=True
    )
    buffer_manager_thread.start()
    
    # ANSI escape codes for screen clear and cursor home
    print(chr(27) + "[2J" + chr(27) + "[;H")
    print(ascii_art)
    print("############################################################")
    
    server_thread = None
    
    audio_stream = args.audio_stream
    audio_host = args.audio_host
    audio_port = args.audio_port
    audio_dir = args.audio_dir
    
    if audio_file_source:
        # Print the hotkeys for user interaction
        print(f"# You can enter text commands using {invert_text(hotkey_prompt)}.\n# To summarize dialogue, use {invert_text(hotkey_summarize)}.\n# Clear message history: {invert_text(hotkey_clear)}. Exit the bot: {invert_text(hotkey_exit)}.")
        print("############################################################\n")
        # Open server with audio directory and port
        # Start the Flask server in a separate thread
        if audio_stream:
            server_thread = ServerThread(host=audio_host, port=audio_port, audio_dir=audio_dir)
            server_thread.start()
            # Set the audio file source to the local server URL
            # unless it is already a valid URL
            if not audio_file_source.startswith(('http://', 'https://')):
                audio_file_source = f"http://{audio_host}:{audio_port}/stream_audio?filename={audio_file_source}"

        # server_thread.join()
        # When server is running:
        audio_recorder.file_source(audio_file_source, stream=audio_stream)
    elif not disable_voice_recognition:
        kwargs = {
            "phrase_time_limit": phrase_time_limit,
            "feedback_word_buffer_limit": feedback_word_buffer_limit,
            "calibration_time": calibration_time,
            "save_audio_to_file": save_audio_to_file
        }
        blink_cursor()
        audio_recorder.start_listening(**kwargs)
        # Print the hotkeys for user interaction
        print(f"# To get a full response, press {invert_text(hotkey_pause)}.\n# You can also enter text commands using {invert_text(hotkey_prompt)}.\n# To summarize dialogue, use {invert_text(hotkey_summarize)}.\n# Clear message history: {invert_text(hotkey_clear)}. Exit the bot: {invert_text(hotkey_exit)}.")
        print("############################################################\n")
    else:
        print(f"# You can enter text commands using {invert_text(hotkey_prompt)}.\n# To summarize dialogue, use {invert_text(hotkey_summarize)}.\n# Clear message history: {invert_text(hotkey_clear)}. Exit the bot: {invert_text(hotkey_exit)}.")
        print("############################################################\n")

    #blink_cursor()

    try:
        # Keep the main thread alive
        while audio_recorder.active:
            time.sleep(1)
    except KeyboardInterrupt:
        # Exit the program on keyboard interrupt
        audio_recorder.active = False
        if server_thread:
            server_thread.shutdown()
    finally:
        # Cleanup the resources and exit the program
        logger.info("Rebuilding vector database index.")
        vector_db.rebuild_index()
        if elevenlabs_streamer:
            elevenlabs_streamer.quit()
        if deepgram_streamer:
            deepgram_streamer.quit()
        audio_recorder.cleanup()
        freeze_cursor()
        logger.info("Program exited.")
        print(Fore.WHITE + "Program exited.\n")


if __name__ == "__main__":
    """ Entry point for the script. """
    main()

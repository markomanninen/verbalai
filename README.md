# VerbalAI

VerbalAI is a near to real-time bidirectional voice AI chatbot implemented as a command-line tool. It utilizes voice-to-text recognition, GPT language model, and text-to-speech service to enable interactive conversations with an AI assistant.

```

██╗   ██╗███████╗██████╗ ██████╗  █████╗ ██╗      █████╗ ██╗
██║   ██║██╔════╝██╔══██╗██╔══██╗██╔══██╗██║     ██╔══██╗██║
██║   ██║█████╗  ██████╔╝██████╔╝███████║██║     ███████║██║
╚██╗ ██╔╝██╔══╝  ██╔══██╗██╔══██╗██╔══██║██║     ██╔══██║██║
 ╚████╔╝ ███████╗██║  ██║██████╔╝██║  ██║███████╗██║  ██║██║
  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝
                                                            
         Bidirectional Voice AI Chatbot - VerbalAI          
```

## Features

- Voice-to-text recognition using Google Speech Recognition library (free)
- Text-to-speech output using Elevenlabs API (free/subscription)
- GPT language model API integration with Anthropic's Claude models (subscription)
- Short and long response modes for intermediate feedback and detailed responses in the conversation
- Hotkey support for various actions (pause, prompt, clear, feedback, summarize, exit)
- Conversation history archive and summarization using GPT model
- Audio input and output recording to a session archive for later examination

## Installation

Make sure you have the latest setuptools installed:

```
pip install --upgrade pip setuptools wheel
```

Create Python environent:

```
python -m venv env
source env/Scripts/activate
```

1. Clone the repository:
   ```
   git clone https://github.com/markomanninen/verbalai.git
   ```

2. Navigate to the project directory:
   ```
   cd verbalai
   ```

3. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```
   Optional MP3 output support requires `ffmpeg` libraries installed as well as `PyAudio` and `PyDub`. You may install Python modules with:
   ```
   pip install -r requirements_mp3.txt
   ```
   but `ffmpeg` requires installing its own libraries: https://ffmpeg.org/

4. Set up the environment variables:
   - Create a `.env` file in the project root directory or copy `.env.example` to `.env`.
   - Add / modify the following variables to the `.env` file:
     ```
     ELEVEN_API_KEY=your_elevenlabs_api_key
     ANTHROPIC_API_KEY=your_anthropic_api_key
     DEEPGRAM_API_KEY=your_deepgram_api_key
     OPENAI_API_KEY=your_openai_api_key
     ```
   - Replace `*****_api_key` with your actual API keys retrieved from the respective service providers.

5. Install the project:
   ```
   pip install -e .
   ```
   or with MP3 support:
   ```
   pip install .[mp3]
   ```


## Usage

To start the VerbalAI chatbot, run the following command:
```
verbalai
```

The chatbot will immediatelly start listening for voice input. You can interact with the application using the following hotkeys:
- `Ctrl+Alt+P`: Pause the listener and get a full response. Toggle resume the voice recognition mode.
- `Ctrl+Alt+F`: Enter text prompt to request short feedback
- `Ctrl+Alt+T`: Enter text prompt for full response
- `Ctrl+Alt+S`: Summarize the previous dialogue
- `Ctrl+Alt+C`: Clear the message history in the session
- `Ctrl+C`: Graceful exit the chatbot

## Customization

You can customize various settings of the VerbalAI chatbot by modifying the command-line arguments.

Some notable options include:
- `-l, --language`: Set the language code for speech recognition (default: en-US)
- `-fl, --feedback_limit`: Set the feedback word buffer threshold limit (default: 25)
- `-v, --voice_id`: Set the Elevenlabs voice ID (default: 29vD33N1CtxCmqQRPOHJ / Drew)
- `-m, --gpt_model`: Set the Anthropic Claude GPT language model (default: claude-3-haiku-20240307)
- `-u, --username`: Set the chat username (default: VerbalHuman)
- `-fs, --file_source`: Instead of microphone input, give a file or URL for inference (default: '')

For more information on the available options, refer to the `verbalai --help` command.

## License

This project is licensed under the [MIT License](LICENSE).

## Contributing

Contributions are welcome! If you find any issues or have suggestions for improvements, please open an issue or submit a pull request.

## Developer notes

**Note:** The package may not run smoothly in a WSL (Windows Subsystem for Linux) environment due to conflicts between the audio drivers of Linux and Windows.

## Command Model Usage

The `test/test_commands.py` script is designed for training and testing the commands module.

The script supports both training and testing modes through command-line arguments. Here's how to use it:

```bash
python test/test_commands.py [--train] [--low_confidence_threshold FLOAT] [--model_path PATH] [--train_file FILE] [--test_file FILE]
```

Default train and test files are in `data` directory.

## Acknowledgements

- [Anthropic](https://www.anthropic.com/) for providing the Claude GPT language models
- [OpenAI](https://www.openai.com/) for providing the OpenAI GPT 3.5/4 language models
- [Elevenlabs](https://www.elevenlabs.io/) for the text-to-speech API
- [Deepgram](https://www.deepgram.com/) for the text-to-speech and speech-to-text API
- [Google Speech Recognition](https://pypi.org/project/SpeechRecognition/) for the voice-to-text recognition functionality

## Similar projects

- https://github.com/gbaptista/ion
- https://github.com/KoljaB/AIVoiceChat
- https://github.com/KoljaB/RealtimeTTS
- https://github.com/lspahija/AIUI
- https://github.com/alesaccoia/VoiceStreamAI
- https://github.com/gkamradt/QuickAgent/
- https://github.com/ccappetta/bidirectional_streaming_ai_voice
- https://medium.com/@sujanxchhetri/creating-a-chatbot-using-socket-io-api-ai-and-web-speech-api-844c3177596b
- https://vapi.ai/

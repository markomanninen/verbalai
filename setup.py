from setuptools import setup, find_packages

setup(
    name='verbalai',
    version='0.1.0',
    description='Bidirectional voice AI chatbot implemented as a console tool',
    author='Marko Manninen',
    author_email='elonmedia@gmail.com',
    packages=find_packages(),
    install_requires=[
        'anthropic',
        'colorama',
        'keyboard',
        'python-dotenv',
        'SpeechRecognition',
        'websockets',
        'deepgram-sdk',
        'openai',
        'flask',
        'werkzeug'
    ],
    extras_require={
        'mp3': [
            'pyaudio',
            'pydub',
        ]
    },
    entry_points={
        'console_scripts': [
            'verbalai = verbalai.verbalai:main',
        ],
    },
)
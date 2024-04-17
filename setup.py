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
        'werkzeug',
        'annoy',
        'transformers',
        'torch'
    ],
    extras_require={
        # TODO: Deepgram requires the following packages to be installed already
        'mp3': [
            'pyaudio',
            'pydub'
        ],
        # Packaged for tool chain, Claude tools and model training libraries
        # These are axperimental and not implemented in the verbalai run flow at the moment
        # but there are tests that can be run with the trained intent prediction model
        'dev': [
            'numpy',
            'pyyaml',
            'scikit-learn',
            'termcolor'
        ]
    },
    entry_points={
        'console_scripts': [
            'verbalai = verbalai.verbalai:main',
        ],
    },
)
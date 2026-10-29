# Copy this file as config.py next to the script you want to run.
# Environment variables with the same names (OPENAI_KEY, TWILIO_SID, ...) override these values.

class Config(object):
    DEBUG = True
    TESTING = False

class DevelopmentConfig(Config):
    OPENAI_KEY = "<OPENAI_API_KEY>"
    ELEVEN_KEY = "<ELEVENLABS_API_KEY>"
    TWILIO_SID = "<TWILIO_ACCOUNT_SID>"
    TWILIO_AUTH = "<TWILIO_AUTH_TOKEN>"
    DEEPGRAM_KEY = "<DEEPGRAM_API_KEY>"
    MODEL_GPT = "gpt-4-0613"  # gpt-3.5-turbo or gpt-4; the late 2023 versions used gpt-4-1106-preview
    TTS_GENERATOR = "elevenlabs"  # elevenlabs or google
    STT_GENERATOR = "deepgram"  # whisper, google or deepgram

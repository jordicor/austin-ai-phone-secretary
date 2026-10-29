import io
import os
import asyncio
import requests
import random
import string
import audioop
import base64
import time
import uuid
import json
import pydub
import logging
import openai
import config
import tempfile
from io import BytesIO
from queue import Queue
from dotenv import load_dotenv
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream, Start, Stop
from twilio.rest import Client
import wave
from queue import Queue
from starlette.responses import Response
from starlette.routing import Route

from deepgram import Deepgram
import asyncio
import aiohttp
import base64
import json
from fastapi import FastAPI, WebSocket, Request
from twilio.twiml.voice_response import VoiceResponse, Connect

from deepgram import Deepgram
import asyncio
from fastapi import FastAPI, WebSocket
import json
import base64

app = FastAPI()

# Set your Twilio and Google Cloud credentials here
account_sid = os.environ.get("TWILIO_SID", config.DevelopmentConfig.TWILIO_SID)
auth_token = os.environ.get("TWILIO_AUTH", config.DevelopmentConfig.TWILIO_AUTH)
twilio_client = Client(account_sid, auth_token)

elevenlabs_key = os.environ.get("ELEVEN_KEY", config.DevelopmentConfig.ELEVEN_KEY)
model_gpt = os.environ.get("MODEL_GPT", config.DevelopmentConfig.MODEL_GPT)
tts_generator = os.environ.get("TTS_GENERATOR", config.DevelopmentConfig.TTS_GENERATOR)
stt_generator = os.environ.get("STT_GENERATOR", config.DevelopmentConfig.STT_GENERATOR)

openai_key = os.environ.get("OPENAI_KEY", config.DevelopmentConfig.OPENAI_KEY)
openai.api_key = openai_key
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'g_credentials.json'


# Your Deepgram API Key
DEEPGRAM_API_KEY = '<DEEPGRAM_API_KEY>'

accumulated_transcript = ""
last_received_time = None


async def setup_deepgram_sdk():
    # Initialize the Deepgram SDK
    deepgram = Deepgram(DEEPGRAM_API_KEY)

    # Create a websocket connection to Deepgram
    try:
        deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'enhanced', 'model' : 'general'})
    except Exception as e:
        print(f'Could not open socket: {e}')
        return None

    # Listen for the connection to close
    deepgram_live.registerHandler(deepgram_live.event.CLOSE, lambda c: print(f'Connection closed with code {c}.'))

    # Listen for any transcripts received from Deepgram and write them to the console
    deepgram_live.registerHandler(deepgram_live.event.TRANSCRIPT_RECEIVED, process_transcription)

    return deepgram_live


def process_transcription(transcription):
    global accumulated_transcript, last_received_time

    current_time = time.time()
    sentence_transcript = transcription["channel"]["alternatives"][0]["transcript"]
    if (sentence_transcript):
        if not transcription["is_final"]:
            last_received_time = current_time
        elif last_received_time is not None and transcription["is_final"] and (current_time - last_received_time) < 2:
            accumulated_transcript += f"  {sentence_transcript}"
            last_received_time = current_time
            print(f"acumulado: {accumulated_transcript}")

        if (current_time - last_received_time) >= 2:
            print(f"FINAL: {accumulated_transcript}")
            accumulated_transcript = ""


@app.websocket("/stream")
async def stream(websocket: WebSocket):
    global deepgram_live

    await websocket.accept()

    try:
        while True:
            message = await websocket.receive_text()

            if message is None:
                continue

            data = json.loads(message)

            if data['event'] == "connected":
                print("Connected Message received: {}".format(data))
            if data['event'] == "start":
                stream_sid = data['start']['streamSid']
                account_sid = data['start']['accountSid']
            if data['event'] == "media":
                audio = base64.b64decode(data['media']['payload'])
                deepgram_live.send(audio)

            if data['event'] == "stop":
                break
            if data['event'] == "mark":
                print('\nMark event')
                break

    except WebSocketDisconnect:
        print("Connection closed")

    except Exception as e:
        print(f"Unexpected error: {str(e)}")

    finally:
        print("Exiting stream(ws) function")
        await websocket.close()

@app.post('/answer')
async def answer(request: Request):
    global call_sid
    global deepgram_live

    deepgram_live = await setup_deepgram_sdk()

    form = await request.form()
    call_sid = form["CallSid"]
    response = VoiceResponse()
    connect = Connect()
    connect.stream(name=f'{call_sid}', url=f'wss://your-domain.example:7777/stream')
    response.append(connect)

    return Response(content=str(response), media_type='text/xml')

if __name__ == '__main__':
    number = twilio_client.incoming_phone_numbers.list()[0]
    print(f'Waiting for calls on {number.phone_number}')
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=7777, ssl_certfile='static/sec/cert.pem', ssl_keyfile='static/sec/privkey.pem')
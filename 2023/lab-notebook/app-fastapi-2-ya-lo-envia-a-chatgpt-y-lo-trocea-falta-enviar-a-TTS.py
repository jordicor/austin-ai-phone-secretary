import io
import re
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
import sys
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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_silence_period())

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

rol = "secretaria"
role_file_path = f"roles/{rol}.txt"
conversations = {}
TTS_Index = {}

async def setup_deepgram_sdk():
    # Initialize the Deepgram SDK
    deepgram = Deepgram(DEEPGRAM_API_KEY)

    try:
        deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'enhanced', 'model' : 'general'})
    except ConnectionClosedError as e:
        print(f'Connection closed with code {e.code} and reason {e.reason}.')
        return None
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
        elif last_received_time is not None and transcription["is_final"]:
            accumulated_transcript += f"  {sentence_transcript}"
            last_received_time = current_time

async def check_silence_period():
    global accumulated_transcript, last_received_time

    while True:
        await asyncio.sleep(0.25)  # Verificar cada cuarto de segundo
        current_time = time.time()

        if last_received_time is not None and (current_time - last_received_time) >= 1.2:
            print(f"FINAL: {accumulated_transcript}")
            await reply_AI(accumulated_transcript)
            accumulated_transcript = ""
            last_received_time = None


# Leer el contenido del archivo de rol
def read_role_prompt(file_path):
    with open(file_path, "r", encoding='utf-8') as file:
        return file.read().strip()        


def initialize_role_message(call_sid):
    global conversations

    if call_sid not in conversations:
        # Inicializar el mensaje de rol a desempeñar
        role_prompt = read_role_prompt(role_file_path)
        conversations[call_sid] = [{"role": "system", "content": role_prompt}]

async def reply_AI(accumulated_transcript):
    initialize_role_message(call_sid)
    message_history = conversations[call_sid]
    
    user_message = {"role": "user", "content": accumulated_transcript}
    message_history.append(user_message)
    
    generate_chat_completion(message_history)
   

def generate_chat_completion(messages, model="gpt-4", temperature=0.5, max_tokens=None):
    global mensajes
    mensajes = []

    if temperature is None:
        temperature = random.uniform(0.4, 0.7)

    if max_tokens is not None:
        max_tokens = max_tokens

    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True
    )

    current_sentence = ""
    tts_break_pattern = '\[TTS_Break\]'

    for chunk in response:
        if "content" in chunk["choices"][0]["delta"]:
            content = chunk["choices"][0]["delta"]["content"]
            for char in content:
                mensajes.append(char)
                if re.search(tts_break_pattern, ''.join(mensajes)):
                    add_to_TTS_index(''.join(mensajes))
                    #print(TTS_Index)                
                    mensajes = []                                

    # Send any remaining text to TTS function
    #if current_sentence.strip():
        #send_to_tts(current_sentence.strip())
        

def add_to_TTS_index(text):
    if '[TTS_Break]' in text:
        content = text.split('[TTS_Break]')[0]
        timestamp = int(time.time())
        TTS_Index[timestamp] = content

@app.get("/audio/{call_sid}/tts")
def get_audio(call_sid: str):
    filtered_text = filter_text(conversations[call_sid][-1]["content"])
    audio_stream = tts11AI_stream(elevenlabs_key, filtered_text)
    return stream_audio_response(audio_stream)


def stream_audio_response(audio_stream):
    def streaming_fn():
        nonlocal audio_stream
        while True:
            chunk = audio_stream.read(1024)
            if not chunk:
                break
            yield chunk

    headers = {
        "Content-Type": "audio/mpeg",
    }
    return StreamingResponse(streaming_fn(), headers=headers)

@app.post('/play/{call_sid}')
def play(request: Request):
    global call_sid

    response = VoiceResponse()

    audio_file_url = f"https://your-domain.example:7777/audio/{call_sid}/tts"
    response.play(audio_file_url)

    connect = Connect()
    connect.stream(name='PrayAI', url=f'wss://your-domain.example:7777/stream')
    response.append(connect)

    return Response(content=str(response), media_type='text/xml')
    
def filter_text(text):
    allowed_characters = (string.ascii_letters + string.digits + string.whitespace +
                          string.punctuation + "áéíóúÁÉÍÓÚüÜñÑ")
    filtered_text = ''.join(c for c in text if c in allowed_characters)
    return filtered_text

def tts11AI_stream(key: str, text: str, voice_id: str = 'TxGEqnHWrfWFTfGW9XjX', stability: float = 0.35, similarity_boost: float = 0.99):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v1",
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost
        }
    }

    response = requests.post(url, json=data, headers=headers, stream=True)

    # Guardar el contenido del stream en un objeto BytesIO
    audio_mp3 = io.BytesIO()
    for chunk in response.iter_content(chunk_size=1024):
        if chunk:
            audio_mp3.write(chunk)

    audio_mp3.seek(0)
    return audio_mp3



@app.websocket("/stream")
async def stream(websocket: WebSocket):
    global deepgram_live
    global call_sid

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
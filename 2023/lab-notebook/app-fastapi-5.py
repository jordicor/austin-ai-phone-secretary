#
# Por ahora funciona bien pero no del todo, tarda mucho, cuando se habla y lo detecta deepgram hay que pararlo 
# (desregistrar y finalizar) el evento que transcript_received porque sino sigue llegando lo que uno habla mientras está procesando GPT y luego el TTS
#
# Por lo pronto las respuestas de GPT si que las trocea según salga [TTS_Break] pero por ahora las va acumulando 
# en un array que luego recorre entero haciendo las peticiones al TTS.
#
#

import io
import re
import os
import aiohttp
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
import threading
import wave
from io import BytesIO
from queue import Queue
from dotenv import load_dotenv
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Value
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream
from twilio.rest import Client
from queue import PriorityQueue, Queue
from starlette.responses import Response
from starlette.routing import Route
from deepgram import Deepgram
from aiohttp import ClientSession

app = FastAPI()

# Credentials here
account_sid = os.environ.get("TWILIO_SID", config.DevelopmentConfig.TWILIO_SID)
auth_token = os.environ.get("TWILIO_AUTH", config.DevelopmentConfig.TWILIO_AUTH)
elevenlabs_key = os.environ.get("ELEVEN_KEY", config.DevelopmentConfig.ELEVEN_KEY)
model_gpt = os.environ.get("MODEL_GPT", config.DevelopmentConfig.MODEL_GPT)
tts_generator = os.environ.get("TTS_GENERATOR", config.DevelopmentConfig.TTS_GENERATOR)
stt_generator = os.environ.get("STT_GENERATOR", config.DevelopmentConfig.STT_GENERATOR)
openai_key = os.environ.get("OPENAI_KEY", config.DevelopmentConfig.OPENAI_KEY)
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'g_credentials.json'
deepgram_key = os.environ.get("DEEPGRAM_KEY", config.DevelopmentConfig.DEEPGRAM_KEY)
twilio_client = Client(account_sid, auth_token)
openai.api_key = openai_key

accumulated_transcript = ""
last_received_time = None

rol = "austin"
role_file_path = f"roles/{rol}.txt"
conversations = {}
TTS_Index = {}
TTS_Queue = {}

async def setup_deepgram_sdk():
    global received_handler
    deepgram = Deepgram(deepgram_key)

    try:
        deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'vad_turnoff': 500, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'enhanced', 'model' : 'general'})
    except ConnectionClosedError as e:
        print(f'Connection closed with code {e.code} and reason {e.reason}.')
        return None
    except Exception as e:
        print(f'Could not open socket: {e}')
        return None

    deepgram_live.registerHandler(deepgram_live.event.CLOSE, lambda c: print(f'Connection closed with code {c}.'))
    received_handler = deepgram_live.registerHandler(deepgram_live.event.TRANSCRIPT_RECEIVED, handle_transcription_event)

    return deepgram_live
    
async def handle_transcription_event(transcription):    
    global accumulated_transcript, last_received_time, sentence_transcript, mensajes, call_sid, deepgram_live, speech_final_detected, received_handler
    mensajes = []
    content = ""

    current_time = time.time()
    sentence_transcript = transcription["channel"]["alternatives"][0]["transcript"]
    if (sentence_transcript):
        if not transcription["speech_final"]:
            last_received_time = current_time
        elif last_received_time is not None and transcription["speech_final"]:
            time_elapsed = current_time - last_received_time
            last_received_time = current_time
            
            print(f"FINAL: {sentence_transcript}")
            #speech_final_detected = 1
            deepgram_live.deregister_handler(deepgram_live.event.TRANSCRIPT_RECEIVED, handle_transcription_event)
            await deepgram_live.finish() #deja de escuchar STT para que no envíe múltiples llamadas a GPT
            
            initialize_role_message(call_sid)
            message_history = conversations[call_sid]
            
            user_message = {"role": "user", "content": sentence_transcript}
            message_history.append(user_message)
            
            first_line = True
            async for line in generate_chat_completion(call_sid, message_history):
                if not line.startswith("data:"):
                    continue
                else:
                    json_data = json.loads(line[5:])
                    finish_reason = json_data["choices"][0].get("finish_reason")
                    
                    if finish_reason == "stop":
                        break
                    
                    if "content" not in json_data["choices"][0]["delta"]:
                        continue
                    else:
                        new_content = json_data["choices"][0]["delta"]["content"]
                        content += new_content
                        if '[TTS_Break]' in content:
                            tts_content = content.split('[TTS_Break]')[0]
                            id_unico = obtener_id_unico()                            
                            if (tts_content):
                                print(f"tts_content: {tts_content}")
                                if call_sid not in TTS_Queue:
                                    TTS_Queue[call_sid] = PriorityQueue()
                                TTS_Queue[call_sid].put((id_unico, tts_content)) 
                            content = ""
            call = twilio_client.calls(call_sid).update(method='POST',url=f'https://your-domain.example:7777/play/{call_sid}')                        
                            
def obtener_id_unico():
    global contador_atomico
    with contador_atomico.get_lock():
        contador_atomico.value += 1
        return contador_atomico.value
        
def read_role_prompt(file_path):
    with open(file_path, "r", encoding='utf-8') as file:
        return file.read().strip()        

def initialize_role_message(call_sid):
    global conversations

    if call_sid not in conversations:
        role_prompt = read_role_prompt(role_file_path)
        conversations[call_sid] = [{"role": "system", "content": role_prompt}]

async def generate_chat_completion(call_sid, messages, model="gpt-4", temperature=0.5, max_tokens=None):
    if temperature is None:
        temperature = random.uniform(0.5, 0.9)

    if max_tokens is not None:
        max_tokens = max_tokens

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_key}",
    }

    url = f"https://api.openai.com/v1/chat/completions"
    data = {
        "model": "gpt-4",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True
    }

    async with ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            async for chunk in response.content:
                yield chunk.decode("utf-8")
        
def add_to_TTS_index(call_sid, text):
    if '[TTS_Break]' in text:
        content = text.split('[TTS_Break]')[0]
        timestamp = int(time.time())
        TTS_Index[call_sid][timestamp] = content


@app.get("/audio/{call_sid}/tts")
async def get_audio(call_sid: str):
    if call_sid in TTS_Queue and not TTS_Queue[call_sid].empty():
        async def streaming_fn():
            nonlocal call_sid

            while call_sid in TTS_Queue and not TTS_Queue[call_sid].empty():
                _, filtered_text = TTS_Queue[call_sid].get()
                audio_stream = tts11AI_stream(elevenlabs_key, filtered_text)

                async for chunk in audio_stream:
                    yield chunk

        headers = {
            "Content-Type": "audio/mpeg",
        }
        return StreamingResponse(streaming_fn(), headers=headers)
    else:
        return JSONResponse(status_code=404, content={"detail": "No audio available"})


def stream_audio_response(audio_streams):
    def streaming_fn():
        nonlocal audio_streams
        for audio_stream in audio_streams:
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

async def tts11AI_stream(key: str, text: str, voice_id: str = 'TxGEqnHWrfWFTfGW9XjX', stability: float = 0.77, similarity_boost: float = 0.99):
    print("entra en tts11AI")
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

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            async for chunk in response.content.iter_chunked(1024):
                if chunk:
                    yield chunk



@app.websocket("/stream")
async def stream(websocket: WebSocket):
    global deepgram_live, call_sid, contador_atomico, speech_final_detected

    contador_atomico = Value("i", 0)  # i indica que el valor es un entero
    
    deepgram_live = await setup_deepgram_sdk()
    speech_final_detected = 0

    await websocket.accept()

    try:
        while True:  # while para mantener la conexión abierta

            while True: #while para ciclo de conversación
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

                # Fin del ciclo de conversación

    except WebSocketDisconnect:
        print("Closed")

    except Exception as e:
        print(f"error: {str(e)}")

    finally:
        print("Exiting")
        await deepgram_live.finish() #deja de escuchar STT para que no envíe múltiples llamadas a GPT
        

@app.post('/answer')
async def answer(request: Request):
    global call_sid

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
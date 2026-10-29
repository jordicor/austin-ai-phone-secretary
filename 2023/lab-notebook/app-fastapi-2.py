#
# Funciona todo, pero el STT (voz a texto) de Deepgram a veces no reconoce del todo bien las palabras o hay palabras de aquí (tipo Premia de Mar que detecta como "Premiere")
# El STT va por streaming en tiempo real y en teoria es un poco más rápido pero menos preciso,no por la velocidad sino por su algoritmo de detección, seguramente en inglés va mejor.
# La gestión de lo que se habla está muy vinculada al STT, cuando llega voz "media" a /stream se lo envía todo a un proceso que está a la escucha y va detectando la frase completa.
# Cuando cree que ya ha pillado una frase completa y cierta pausa entonces devuelve "speech_final" en true, de ahí es cuando lo envío a GPT.
# Filtra que no esté vacía la frase porque puede enviar "speech_final" y que no haya nada.
# De ahí inicializa la conversación con GPT en la que añade los parámetros iniciales System donde lee el rol de un txt y añade la primera pregunta al historial de mensajes
# Y hace la pregunta a GPT, que devolverá la respuesta en streaming.
# En el streaming va cortando lo que llega cada vez que ponga [TTS_Break], para que lo haga se le ha dado una instrucción en el prompt a GPT para que trocee sus respuestas poniendo ese tag.
# Cada vez que se detecte el tag se enviará a la api de Elevenlabs, la cual responde en formato MP3 y tiene que ser convertido a mulaw (mucha menos calidad)
# para luego enviarlo a Twilio en streaming a Twilio codificado en base64 al socket que se ha abierto en el stream.
# En el socket se puede recibir o enviar "del tirón", está abierto para ambas partes y lo que se envíe, por ejemplo "media" pues se escuchará.
# De este modo se mantiene siempre el mismo stream abierto, no se sale de él y siempre está a la escucha. Por lo cual no cuelga la llamada.
# Se puede hacer que tenga más calidad redireccionando a /play/{call_sid}/tts y de ahí lanzarle el streaming el MP3 de Elevenlabs 
# pero habría que crear una cola de espera mientras se reproduce el audio ya que es async y si se hace del tirón se corta, porque tras
# reproducir los MP3 hay que redireccionar de nuevo hacia /stream e ir pegando "saltos" así. Tiene más calidad de audio pero falta la cola y también tarda más entre conectar de un lado al otro.
#


import io
import os
import re
import sys
import json
import time
import uuid
import wave
import pydub
import base64
import config
import openai
import random
import string
import aiohttp
import asyncio
import audioop
import logging
import requests
import tempfile
import threading
from io import BytesIO
from queue import Queue
from asyncio import sleep
from deepgram import Deepgram
from dotenv import load_dotenv
from pydub import AudioSegment
from twilio.rest import Client
from aiohttp import ClientSession
from multiprocessing import Value
from starlette.routing import Route
from queue import PriorityQueue, Queue
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse

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

#rol = "secretaria"
rol = "austin"
role_file_path = f"roles/{rol}.txt"
conversations = {}
TTS_Index = {}
TTS_Queue = {}
TTS_Audio = {}
connected_websockets = {}
twilio_stream = {}

async def setup_deepgram_sdk():
    global received_handler
    deepgram = Deepgram(deepgram_key)

    try:
        deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'enhanced', 'model' : 'general'})
    except ConnectionClosedError as e:
        print(f'Connection closed with code {e.code} and reason {e.reason}.')
        return None
    except Exception as e:
        print(f'Could not open socket: {e}')
        return None

    deepgram_live.registerHandler(deepgram_live.event.CLOSE, handle_closing_event)
    received_handler = deepgram_live.registerHandler(deepgram_live.event.TRANSCRIPT_RECEIVED, handle_transcription_event)

    return deepgram_live
    
    
async def handle_closing_event(ecode):
    if (ecode != 1000):
        print(f'Connection closed with code {ecode}.')
   
async def handle_transcription_event(transcription):    
    global accumulated_transcript, last_received_time, sentence_transcript, mensajes, call_sid, deepgram_live, speech_final_detected, received_handler, connected_websockets
    
    mensajes = []
    content = ""

    current_time = time.time()
    
    if "channel" in transcription:
        sentence_transcript = transcription["channel"]["alternatives"][0]["transcript"]
    
    if (sentence_transcript):
        if not transcription["speech_final"]:
            last_received_time = current_time
            
        elif last_received_time is not None and transcription["speech_final"]:
            last_received_time = current_time
            
            print(f"FINAL: {sentence_transcript}")
            deepgram_live.deregister_handler(deepgram_live.event.TRANSCRIPT_RECEIVED, handle_transcription_event)
            
            initialize_role_message(call_sid)
            message_history = conversations[call_sid]
            
            user_message = {"role": "user", "content": sentence_transcript}
            message_history.append(user_message)

            full_content = ""
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
                        full_content += new_content
                        content += new_content
                        if '[TTS_Break]' in content:
                            tts_content = content.split('[TTS_Break]')[0]
                            if (tts_content):
                                content = ""
                                print(f"tts_content: {tts_content}")
                                await tts11AI_stream(elevenlabs_key, tts_content)                                

            gpt_message = {"role": "user", "content": full_content}
            message_history.append(gpt_message)
            
            received_handler = deepgram_live.registerHandler(deepgram_live.event.TRANSCRIPT_RECEIVED, handle_transcription_event)
            #print("DeepgramLive Activado")

        
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
        temperature = random.uniform(0.7, 0.9)

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


async def send_audio_to_twilio(ws: WebSocket, chunk: bytes, streamSid: str):
    media_data = {
        "event": "media",
        "streamSid": streamSid,
        "media": {
            "payload": base64.b64encode(chunk).decode("utf-8")
        }
    }
    await ws.send_json(media_data)
    

async def send_mark_to_twilio(ws: WebSocket, streamSid: str):
    media_data = {
        "event": "mark",
        "streamSid": streamSid,
        "mark": {
            "name": "TTS_Audio"
        }
    }
    await ws.send_json(media_data)

    
def filter_text(text):
    allowed_characters = (string.ascii_letters + string.digits + string.whitespace +
                          string.punctuation + "áéíóúÁÉÍÓÚüÜñÑ")
    filtered_text = ''.join(c for c in text if c in allowed_characters)
    return filtered_text


async def tts11AI_stream(key: str, text: str, voice_id: str = '9MuZVz9czdPipoZ12F8t', stability: float = 0.57, similarity_boost: float = 0.99):
    global connected_websockets, twilio_stream, call_sid
    
    ws = connected_websockets[call_sid]
    streamSid = twilio_stream[call_sid]['start']['streamSid']

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

    audio_mp3 = io.BytesIO()
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            async for chunk in response.content.iter_chunked(2048):
                if chunk:
                    audio_mp3.write(chunk)
        audio_mp3.seek(0)

    # Utilizar pydub para cargar el archivo mp3
    audio = AudioSegment.from_mp3(audio_mp3)

    # Convertir el audio a formato WAV
    audio_wav = io.BytesIO()
    audio.export(audio_wav, format="wav")
    audio_wav.seek(0)

    # Utilizar pydub para convertir el audio en formato WAV al formato Mulaw (u-law) con una frecuencia de muestreo de 8000Hz
    audio = AudioSegment.from_wav(audio_wav)
    audio = audio.set_frame_rate(8000).set_sample_width(2).set_channels(1)

    # Convertir el audio a Mulaw usando audioop.lin2ulaw
    audio_data = audio.raw_data
    audio_data_mulaw = audioop.lin2ulaw(audio_data, audio.sample_width)

    # Enviar el audio por stream a Twilio
    CHUNK_SIZE = 512
    for i in range(0, len(audio_data_mulaw), CHUNK_SIZE):
        chunk = audio_data_mulaw[i:i+CHUNK_SIZE]
        await send_audio_to_twilio(ws, chunk, streamSid)


@app.websocket("/stream")
async def stream(websocket: WebSocket):
    global deepgram_live, call_sid, speech_final_detected
    global connected_websockets, twilio_stream

    deepgram_live = await setup_deepgram_sdk()
    speech_final_detected = 0

    connected_websockets[call_sid] = websocket

    await websocket.accept()

    try:
        while True:  # while para mantener la conexión abierta

            while True: #while para ciclo de conversación
                message = await websocket.receive_text()

                if message is None:
                    continue

                data = json.loads(message)

                if data['event'] == "start":
                    print(f"Connected START received, call_sid: {call_sid}")
                    twilio_stream[call_sid] = data
                    stream_sid = data['start']['streamSid']
                    account_sid = data['start']['accountSid']

                if data['event'] == "media":
                    audio = base64.b64decode(data['media']['payload'])
                    if data['media']['track'] == 'inbound':
                        deepgram_live.send(audio)

                if data['event'] == "stop":
                    break
                if data['event'] == "mark":
                    print('\nMark event')
                    break

                # Fin del ciclo de conversación

    except WebSocketDisconnect:
        pass
        #print("Closed")

    except Exception as e:
        print(f"error: {str(e)}")

    finally:
        #print("Exiting")
        await deepgram_live.finish()
        del connected_websockets[call_sid] 


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
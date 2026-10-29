import io
import os
import asyncio
import requests
import random
import string
import audioop
import base64
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
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import texttospeech_v1 as texttospeech
import wave
from queue import Queue
from starlette.responses import Response
from starlette.routing import Route

from fastapi.responses import StreamingResponse

app = FastAPI()

call_sid = None
load_dotenv()
API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Set your Twilio and Google Cloud credentials here
account_sid = os.environ.get("TWILIO_SID", config.DevelopmentConfig.TWILIO_SID)
auth_token = os.environ.get("TWILIO_AUTH", config.DevelopmentConfig.TWILIO_AUTH)
twilio_client = Client(account_sid, auth_token)
deepgram_key = os.environ.get("DEEPGRAM_KEY", config.DevelopmentConfig.DEEPGRAM_KEY)
elevenlabs_key = os.environ.get("ELEVEN_KEY", config.DevelopmentConfig.ELEVEN_KEY)
model_gpt = os.environ.get("MODEL_GPT", config.DevelopmentConfig.MODEL_GPT)
tts_generator = os.environ.get("TTS_GENERATOR", config.DevelopmentConfig.TTS_GENERATOR)
stt_generator = os.environ.get("STT_GENERATOR", config.DevelopmentConfig.STT_GENERATOR)

openai_key = os.environ.get("OPENAI_KEY", config.DevelopmentConfig.OPENAI_KEY)

openai.api_key = openai_key
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'g_credentials.json'

audio_queue = Queue()

rol = "santa-improved"
role_file_path = f"roles/{rol}.txt"
conversations = {}

def generate_chat_completion(messages, model="gpt-3.5-turbo", temperature=1, max_tokens=None):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_key}",
    }

    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    if max_tokens is not None:
        data["max_tokens"] = max_tokens

    response = requests.post(API_ENDPOINT, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        raise Exception(f"Error {response.status_code}: {response.text}")

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
    
    
def rms(audio):
    return audioop.rms(audio, 2)
    
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


def text_to_speech(ws, streamSid, text, tts_generator):
    filtered_text = filter_text(text)
    if tts_generator == "google":
        client = texttospeech.TextToSpeechClient()
        input_text = texttospeech.SynthesisInput(text=filtered_text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="es-ES", ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            sample_rate_hertz=16000,
        )

        response = client.synthesize_speech(
            input=input_text, voice=voice, audio_config=audio_config
        )
        return response.audio_content
    elif tts_generator == "elevenlabs":
        tts11AI_stream(ws, streamSid, elevenlabs_key, filtered_text)


async def send_audio_to_twilio(ws: WebSocket, chunk: bytes, streamSid: str):
    media_data = {
        "event": "media",
        "streamSid": streamSid,
        "media": {
            "payload": base64.b64encode(chunk).decode("utf-8")
        }
    }
    await ws.send_json(media_data)
    
def create_wav():
    global call_sid
    output_file = wave.open(f"audio/{call_sid}.wav", "wb")
    output_file.setnchannels(1)
    output_file.setsampwidth(2)
    output_file.setframerate(8000)
    return output_file

def random_temperature(min_value=0.5, max_value=0.8):
    return random.uniform(min_value, max_value)
    
def send_messages(messages, message_history):
    return openai.ChatCompletion.create(
        model=model_gpt,
        messages=message_history + messages,
        temperature=random_temperature()
    )
    
def speech_to_text(audio_file, stt_generator):
    if stt_generator == "google":
        audio_data = audio_file.read()
        client = speech.SpeechClient()

        config = {
            "language_code": "es-ES",
            "sample_rate_hertz": 8000,
            "encoding": speech.RecognitionConfig.AudioEncoding.LINEAR16,
        }
        audio = {"content": audio_data}

        response = client.recognize(config=config, audio=audio)

        for result in response.results:
            return result.alternatives[0].transcript

    elif stt_generator == "whisper":
        return openai.Audio.transcribe("whisper-1", audio_file).text    
    elif stt_generator == "deepgram":
        audio_data = audio_file.read()
        url = "https://api.deepgram.com/v1/listen"
        headers = {
            "Content-Type": "audio/wav",
            "Authorization": f"Token {deepgram_key}",
        }
        response = requests.post(url, headers=headers, data=audio_data)

        if response.status_code == 200:
            response_json = response.json()
            return response_json["results"]["channels"][0]["alternatives"][0]["transcript"]
        else:
            raise Exception(f"Error {response.status_code}: {response.text}")
    

async def reply_streaming(output_file, ws, streamSid):
    global call_sid

    print('\nProcesando respuesta..')

    output_file.close()
    audio_file = open(f"audio/{call_sid}.wav", "rb") 
    transcribed_text = speech_to_text(audio_file, stt_generator)

    print(transcribed_text)
    
    #Creo historial de mensajes con ChatGPT usando call_sid como identificador común de la llamada que se mantiene aunque hayan redirecciones.
    #Se añade el prompt inicial de ChatGPT al historial de mensajes
    initialize_role_message(call_sid)
    message_history = conversations[call_sid]
    
    #Se añade en el historial el mensaje del usuario de lo que se ha dicho en el micrófono 
    user_message = {"role": "user", "content": transcribed_text}
    message_history.append(user_message)
    
    #Se envía a ChatGPT el historial de mensajes (system+assistant+ lo último que ha dicho user) para que responda y lo guarde en response_text
    response_text = generate_chat_completion(message_history)
    print(response_text)
    #Se añade al historial de mensajes lo que ha respondido ChatGPT para que cuando se entre de nuevo a responder tenga contexto de las cosas que ha respondido
    gpt_message = {"role": "assistant", "content": response_text}
    message_history.append(gpt_message)


@app.post('/answer')
async def answer(request: Request):
    global call_sid

    form = await request.form()
    call_sid = form["CallSid"]

    response = VoiceResponse()
    #audio_file_url = f"https://your-service.twil.io/assets/IntroSantaElliElevenlabs.mp3"
    #response.play(audio_file_url)

    connect = Connect()
    connect.stream(name=f'{call_sid}', url=f'wss://your-domain.example:7777/stream')

    response.append(connect)

    return Response(content=str(response), media_type='text/xml')


@app.websocket("/stream")
async def stream(websocket: WebSocket):
    global call_sid

    await websocket.accept()
    ha_respondido = 0

    try:
        while True:  # while para mantener la conexión abierta
            silence_duration = 0
            audio_detected = False
            output_file = create_wav()

            while True:  # Este while maneja cada ciclo de conversación
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
                    audio = audioop.ulaw2lin(audio, 2)
                    audio = audioop.ratecv(audio, 2, 1, 8000, 8000, None)[0]

                    rms_value = rms(audio)
                    silence_threshold = 1200
                    if rms_value < silence_threshold:
                        sample_time = len(audio) / (2 * 8000)
                        silence_duration += sample_time
                    else:
                        silence_duration = 0
                        audio_detected = True

                    if silence_duration < 3:
                        output_file.writeframes(audio)

                    if silence_duration > 2 and audio_detected:
                        if ha_respondido < 1:
                            ha_respondido = 1
                            await reply_streaming(output_file, websocket, stream_sid)
                            call = twilio_client.calls(call_sid).update(method='POST',url=f'https://your-domain.example:7777/play/{call_sid}')                        

                            break

                if data['event'] == "stop":
                    break
                if data['event'] == "mark":
                    print('\nMark event')
                    break
            # Fin del ciclo de conversación

    except WebSocketDisconnect:
        print("Connection closed")

    except Exception as e:
        print(f"Unexpected error: {str(e)}")

    finally:
        print("Exiting stream(ws) function")
        #await websocket.close()
		
if __name__ == '__main__':
    number = twilio_client.incoming_phone_numbers.list()[0]
    print(f'Waiting for calls on {number.phone_number}')
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=7777, ssl_certfile='static/sec/cert.pem', ssl_keyfile='static/sec/privkey.pem')	
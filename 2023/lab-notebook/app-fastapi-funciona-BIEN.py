import os
import requests
import random
import string
import audioop
import base64
import uuid
import json
import os
import logging
import openai
import config
from io import BytesIO
from dotenv import load_dotenv
from pydub import AudioSegment
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

API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

app = FastAPI()
app.mount("/audio", StaticFiles(directory="audio"), name="audio")

call_sid = None

load_dotenv()

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

input_queue = Queue()

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

@app.get('/audio/{filename}')
async def serve_audio(filename: str):
    audio_directory = "audio"
    return FileResponse(f"{audio_directory}/{filename}")

@app.post('/play')
async def play(request: Request):
    global call_sid

    # Replace request.form with request.form()
    form = await request.form()
    call_sid = form["CallSid"]

    response = VoiceResponse()

    audio_file_url = f"https://your-domain.example:7777/audio/tts_{call_sid}.mp3"
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
    
    
def tts11AI(key: str, text: str, voice_id: str = 'TxGEqnHWrfWFTfGW9XjX', stability: float = 0.18, similarity_boost: float = 0.99) -> bytes:
    # create a session object 
    s = requests.Session()

    # set the headers
    headers = {
        "accept": "audio/mpeg",
        "xi-api-key": key,
        "Content-Type": "application/json",
    }

    # set the payload
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v1",
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost
        }
    }

    # make the post request
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    try:
        r = s.post(url, data=json.dumps(payload), headers=headers, timeout=60)
        if r.status_code != 200:
            return None

        # return the response content as bytes
        return r.content

    except requests.exceptions.Timeout:
        return None

    except Exception as e:
        print(f'Unexpected error: {e}')
        return None
   

def text_to_speech(text, tts_generator):
    filtered_text = filter_text(text)
    if (tts_generator == "google"):
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
    elif (tts_generator == "elevenlabs"):
        # Use ElevenlabsAI 
        response = tts11AI(elevenlabs_key, filtered_text)

        if response is None:
            return jsonify({"error": "Error generating audio with ElevenlabsAI"}), 500

        return response
    

def audio_tts_response(transcribed_text):
    global call_sid

    audio_content = text_to_speech(transcribed_text, tts_generator)
    audio_file = open(f"audio/tts_{call_sid}.mp3", "wb")
    audio_file.write(audio_content)
    audio_file.close()

def create_wav():
    global call_sid
    # Crear archivo wav con el nombre de la sesión de la llamada
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
    

def reply_streaming(output_file, ws, streamSid):
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
    
    #Pasa a voz sintética (TTS) la respuesta de ChatGPT 
    audio_data = audio_tts_response(response_text)


@app.post('/answer')
async def answer(request: Request):
    global call_sid

    form = await request.form()
    call_sid = form["CallSid"]

    response = VoiceResponse()
    audio_file_url = f"https://your-domain.example:7777/audio/IntroSantaElliElevenlabs.mp3"
    response.play(audio_file_url)

    connect = Connect()
    connect.stream(name=f'{call_sid}', url=f'wss://your-domain.example:7777/stream')

    response.append(connect)

    return Response(content=str(response), media_type='text/xml')


@app.websocket("/stream")
async def stream(websocket: WebSocket):
    global call_sid

    silence_duration = 0
    ha_respondido = 0
    audio_detected = False

    output_file = create_wav()

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
                audio = audioop.ulaw2lin(audio, 2)
                audio = audioop.ratecv(audio, 2, 1, 8000, 8000, None)[0]

                rms_value = rms(audio)
                silence_threshold = 300
                if rms_value < silence_threshold:
                    sample_time = len(audio) / (2 * 8000)
                    silence_duration += sample_time
                else:
                    silence_duration = 0
                    audio_detected = True

                if silence_duration < 2:
                    output_file.writeframes(audio)

                if silence_duration > 2 and audio_detected:
                    if ha_respondido < 1:
                        ha_respondido = 1

                        reply_streaming(output_file, websocket, stream_sid)
                        call = twilio_client.calls(call_sid).update(method='POST', url=f'https://your-domain.example:7777/play')
                        break

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

		
if __name__ == '__main__':
    number = twilio_client.incoming_phone_numbers.list()[0]
    print(f'Waiting for calls on {number.phone_number}')
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=7777, ssl_certfile='static/sec/cert.pem', ssl_keyfile='static/sec/privkey.pem')		
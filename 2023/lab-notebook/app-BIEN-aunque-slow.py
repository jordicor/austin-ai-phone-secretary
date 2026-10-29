import requests
import random
import audioop
import base64
import uuid
import json
import os
import logging
import openai
import config
from io import BytesIO
from pydub import AudioSegment
from flask import Flask, request, send_from_directory
from flask import jsonify, session
from flask_sock import Sock, ConnectionClosed
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream, Start, Stop
from twilio.rest import Client
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import texttospeech_v1 as texttospeech
import wave
from queue import Queue


API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

app = Flask(__name__)
sock = Sock(app)

call_sid = None

# Configura tus credenciales de Twilio y Google Cloud aquí
app.config.from_object(config.config['development'])

account_sid = config.DevelopmentConfig.TWILIO_SID
auth_token = config.DevelopmentConfig.TWILIO_AUTH
twilio_client = Client(account_sid, auth_token)

elevenlabs_key = config.DevelopmentConfig.ELEVEN_KEY
model_gpt = config.DevelopmentConfig.MODEL_GPT
tts_generator = config.DevelopmentConfig.TTS_GENERATOR
stt_generator = config.DevelopmentConfig.STT_GENERATOR

openai_key = config.DevelopmentConfig.OPENAI_KEY

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


@app.route('/audio/<path:filename>')
def serve_audio(filename):
    audio_directory = "audio"
    return send_from_directory(audio_directory, filename)
    
@app.route('/play', methods=['POST'])
def play():
    global call_sid
#    call = twilio_client.calls(call_sid).update(twiml=f'<Response><Say>Hi there! This is your answer:</Say><Play>https://your-domain.example/audio/tts_output.mp3</Play></Response>')

    response = VoiceResponse()

    audio_file_url = f"https://your-domain.example/audio/tts_{call_sid}.mp3"
    response.play(audio_file_url)

    connect = Connect()
    connect.stream(name='PrayAI', url=f'wss://{request.host}/stream')

    response.append(connect)    

    return str(response), 200, {'Content-Type': 'text/xml'}

def rms(audio):
    return audioop.rms(audio, 2)
    
    
    
def tts11AI(key: str, text: str, voice_id: str = 'TxGEqnHWrfWFTfGW9XjX', stability: float = 0.75, similarity_boost: float = 0.75) -> bytes:
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
    if (tts_generator == "google"):
        client = texttospeech.TextToSpeechClient()
        input_text = texttospeech.SynthesisInput(text=text)
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
        response = tts11AI(elevenlabs_key, text)

        if response is None:
            return jsonify({"error": "Error generating audio with ElevenlabsAI"}), 500

        return response
    

def audio_tts_response(transcribed_text):
    global call_sid

    audio_content = text_to_speech(transcribed_text, tts_generator)
    audio_file = open(f"audio/tts_{call_sid}.mp3", "wb")
    audio_file.write(audio_content)
    audio_file.close()


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


# RUTA INICIAL para recibir la llamada
@app.route('/answer', methods=['POST'])
def answer():
    global call_sid
    
    print(f'Llamada de {request.form["From"]}')
    
    call_sid = request.form["CallSid"]
    
    response = VoiceResponse()
    response.say("Deja tu mensaje", voice='alice', language='es-ES')

    connect = Connect()
    connect.stream(name=f'{call_sid}', url=f'wss://{request.host}/stream')
    
    response.append(connect)

    return str(response), 200, {'Content-Type': 'text/xml'}

def create_wav():
    global call_sid
    # Crear archivo wav con el nombre de la sesión de la llamada
    output_file = wave.open(f"audio/{call_sid}.wav", "wb")
    output_file.setnchannels(1)
    output_file.setsampwidth(2)
    output_file.setframerate(8000)
    return output_file

    
@sock.route('/stream')
def stream(ws):
    global call_sid
    
    silence_duration = 0
    ha_respondido = 0
    audio_detected = False  # Agregar esta variable para rastrear si se ha detectado audio
   
    output_file = create_wav()
    
    try:
        while True:
            message = ws.receive()
            
            if message is None:
                continue
            
            # Messages are a JSON encoded string
            data = json.loads(message)
            
            # Using the event type you can determine what type of message you are receiving
            if data['event'] == "connected":
                print("Connected Message received: {}".format(data))
            if data['event'] == "start":
                #print("Start Message received: {}".format(data))
                stream_sid = data['start']['streamSid']
                account_sid = data['start']['accountSid']
            if data['event'] == "media":
                #print(data['media']['payload'])
                audio = base64.b64decode(data['media']['payload'])
                audio = audioop.ulaw2lin(audio, 2)
                audio = audioop.ratecv(audio, 2, 1, 8000, 8000, None)[0]

                # Calcular el tiempo de silencio
                rms_value = rms(audio)
                silence_threshold = 300
                if rms_value < silence_threshold:
                
                    sample_time = len(audio) / (2 * 8000)  # 2 bytes por muestra y 8000 muestras por segundo
                    silence_duration += sample_time
                else:
                    silence_duration = 0
                    audio_detected = True  # Marcar que se ha detectado audio cuando el nivel de sonido está por encima del umbral

                if silence_duration < 2:
                    output_file.writeframes(audio) # Solo guarda en el wav cuando hay sonido que se quiera transcribir, los silencios los omite

                # Salir del bucle si se detecta silencio durante más de 2 segundos y se ha detectado audio previamente
                if silence_duration > 2 and audio_detected:
                    #ws.close()
                    if ha_respondido < 1:
                        ha_respondido = 1
                        reply_streaming(output_file, ws, stream_sid)
                        call = twilio_client.calls(call_sid).update(method='POST',url='https://your-domain.example/play')                        
                        break
                        
            if data['event'] == "stop":
                print("ha pedido STOP")
                
                break
            if data['event'] == "mark":
                print('\nMark event')
                break
                
                
    except ConnectionClosed:
        print("Connection closed")
        
    except Exception as e:  # Agregar este bloque except para capturar otras excepciones
        print(f"Unexpected error: {str(e)}")
    except TwilioRestException as e:
        print(e)        
    finally:  # Agregar este bloque finally para capturar el final de la función
        print("Exiting stream(ws) function")    
        ws.close()
        
       
if __name__ == '__main__':
    number = twilio_client.incoming_phone_numbers.list()[0]
    print(f'Waiting for calls on {number.phone_number}')
    app.run(host='0.0.0.0', port='443', debug=True, ssl_context=('static/sec/cert.pem', 'static/sec/privkey.pem'))     

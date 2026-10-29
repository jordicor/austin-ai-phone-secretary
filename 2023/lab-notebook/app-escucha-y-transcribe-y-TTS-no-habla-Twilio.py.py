import audioop
import base64
import json
import os
import logging
import openai
from flask import Flask, request
from flask_sock import Sock, ConnectionClosed
#from flask_sockets import Sockets
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream, Start, Stop
from twilio.rest import Client
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import texttospeech_v1 as texttospeech
import wave

app = Flask(__name__)
sock = Sock(app)

# Configura tus credenciales de Twilio y Google Cloud aquí
account_sid = "<TWILIO_ACCOUNT_SID>"
auth_token = "<TWILIO_AUTH_TOKEN>"
twilio_client = Client(account_sid, auth_token)

openai.api_key = "<OPENAI_API_KEY>"
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'g_credentials.json'

def rms(audio):
    return audioop.rms(audio, 2)

def transcribe_audio(audio_data):
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(content=audio_data)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="es-ES",
    )

    response = client.recognize(config=config, audio=audio)
    return response.results[0].alternatives[0].transcript

def text_to_speech(text):
    client = texttospeech.TextToSpeechClient()
    input_text = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="es-ES", ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = client.synthesize_speech(
        input=input_text, voice=voice, audio_config=audio_config
    )
    return response.audio_content

def play_tts_response(transcribed_text):
    audio_content = text_to_speech(transcribed_text)
    audio_file = open("tts_output.mp3", "wb")
    audio_file.write(audio_content)
    audio_file.close()
    


def stop_streaming(output_file):
    print('\nStreaming has stopped')
    output_file.close()
    audio_file = open("output.wav", "rb") 
    transcribed_text = openai.Audio.transcribe("whisper-1", audio_file).text
    print(transcribed_text)
    play_tts_response(transcribed_text)


# Ruta para recibir la llamada
@app.route('/answer', methods=['POST'])
def answer():
    print(f'Llamada de {request.form["From"]}')
    response = VoiceResponse()
    response.say('Deja tu mensaje')
    #start = Start()
    #start.stream(name='PrayAI', url=f'wss://{request.host}/stream')
    #response.append(start)
    connect = Connect()
    connect.stream(name='PrayAI', url=f'wss://{request.host}/stream')
    response.append(connect)

#    response.pause(length=60)

    return str(response), 200, {'Content-Type': 'text/xml'}


# Ruta para reproducir la respuesta TTS
@app.route('/play_tts_response', methods=['POST'])
def play_response():
    response = VoiceResponse()
    response.play("tts_output.mp3")
    response.hangup()
    return str(response), 200, {'Content-Type': 'text/xml'}
    

@sock.route('/stream')
def stream(ws):
    print("entra stream")
    silence_duration = 0
    
    # Crear archivo output.wav
    output_file = wave.open("output.wav", "wb")
    output_file.setnchannels(1)
    output_file.setsampwidth(2)
    output_file.setframerate(16000)
    
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
                print("Start Message received: {}".format(data))
                stream_sid = data['start']['streamSid']
                account_sid = data['start']['accountSid']
                call_sid = data['start']['callSid']                
            if data['event'] == "media":
                print("Llega media: {}".format(data))            
                audio = base64.b64decode(data['media']['payload'])
                audio = audioop.ulaw2lin(audio, 2)
                audio = audioop.ratecv(audio, 2, 1, 8000, 16000, None)[0]
                output_file.writeframes(audio)

                # Calcular el tiempo de silencio
                rms_value = rms(audio)
                silence_threshold = 300  # Ajustar valor según se quiera
                if rms_value < silence_threshold:
                    sample_time = len(audio) / (2 * 16000)  # 2 bytes por muestra y 16000 muestras por segundo
                    silence_duration += sample_time
                else:
                    silence_duration = 0

                # Salir del bucle si se detecta silencio durante más de 5 segundos
                if silence_duration > 2:
                    #stream = twilio_client.calls(call_sid).streams('PrayAI').update(status='stopped')
                    #print(stream.name)
                    ws.close()
                    stop_streaming(output_file)
                    break
    
            if data['event'] == "stop":
                stop_streaming(output_file)
                break
            if data['event'] == "mark":
                print('\nMark event')
                break
    except ConnectionClosed:
        print("Connection closed")
        stop_streaming(output_file)
        
        

if __name__ == '__main__':
    from pyngrok import ngrok
    port = 7777
    public_url = ngrok.connect(port, bind_tls=True).public_url
    number = twilio_client.incoming_phone_numbers.list()[0]
    number.update(voice_url=public_url + '/answer')
    print(f'Waiting for calls on {number.phone_number}')

    app.run(port=port, debug=True)
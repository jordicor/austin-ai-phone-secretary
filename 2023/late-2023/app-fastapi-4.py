###########
# Flujo de la app: llamada de teléfono entra a twilio y la primera en ejecutarse es la funcíon Answer, de ahí la envia a la función Stream, la cual inicializa otras, entre ellas Deepgram que se quedará a la escucha de recibir audio desde Stream y lo transcribirá.
# Cada vez que transcriba algo se activa la función get_transcription_add_call_sid que recibe la transcripción, de ahí la interpreta, la envía a GPT y recibe la respuesta que también interpreta y pasa a TTS para responder por voz o ejecuta las funciones que haya pedido GPT.
###########
# Cambio respecto a la 3.7 -> le añado la opción de recibir streaming de texto a Elevenlabs
###########


# Importamos las librerías necesarias
import io
import os
import re
import re
import sys
import json
import time
import time
import uuid
import wave
import emoji
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
import threading
import numpy as np
from io import BytesIO
from queue import Queue
from asyncio import sleep
from scipy.io import wavfile
from datetime import datetime
from deepgram import Deepgram
from dotenv import load_dotenv
from pydub import AudioSegment
from twilio.rest import Client
from aiohttp import ClientSession
from multiprocessing import Value
from urllib.parse import urlencode
from starlette.routing import Route
from queue import PriorityQueue, Queue
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
from functions import FUNCTIONS, CISCOPHONE
from concurrent.futures import ThreadPoolExecutor
from twilio.base.exceptions import TwilioRestException
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse

import elevenlabs
from elevenlabs import generate, play

from asyncio import ensure_future

app = FastAPI()

# Inicializamos los credenciales
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'g_credentials.json'
model_gpt = os.environ.get("MODEL_GPT", config.DevelopmentConfig.MODEL_GPT)
openai_key = os.environ.get("OPENAI_KEY", config.DevelopmentConfig.OPENAI_KEY)
account_sid = os.environ.get("TWILIO_SID", config.DevelopmentConfig.TWILIO_SID)
auth_token = os.environ.get("TWILIO_AUTH", config.DevelopmentConfig.TWILIO_AUTH)
elevenlabs_key = os.environ.get("ELEVEN_KEY", config.DevelopmentConfig.ELEVEN_KEY)
deepgram_key = os.environ.get("DEEPGRAM_KEY", config.DevelopmentConfig.DEEPGRAM_KEY)
stt_generator = os.environ.get("STT_GENERATOR", config.DevelopmentConfig.STT_GENERATOR)
tts_generator = os.environ.get("TTS_GENERATOR", config.DevelopmentConfig.TTS_GENERATOR)

openai.api_key = openai_key
twilio_client = Client(account_sid, auth_token)

accumulated_transcript = ""
last_received_time = None

rol = "austin-4"
role_file_path = f"roles/{rol}.txt"
conversations = {}
#boss_calling =  {}
TTS_Index = {}
TTS_Queue = {}
TTS_Audio = {}
connected_websockets = {}
twilio_stream = {}
gpt_arguments = {}

query_params = ""

async def setup_deepgram_sdk(call_sid, boss_calling):
    global received_handler
    deepgram = Deepgram(deepgram_key)

    try:
        #deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'enhanced', 'model' : 'general'})
        deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'nova', 'model' : 'general'})
       
    except ConnectionClosedError as e:
        print(f'Connection closed with code {e.code} and reason {e.reason}.')
        return None
    except Exception as e:
        print(f'Could not open socket: {e}')
        return None

    # Añade un evento a la escucha en el caso de cerrar el streaming a la escucha.
    deepgram_live.registerHandler(deepgram_live.event.CLOSE, handle_closing_event)
    

    async def get_transcription_add_call_sid(transcription):
        global accumulated_transcript, last_received_time, sentence_transcript, mensajes, deepgram_live, received_handler, connected_websockets
        
        id_unico = random.uniform(1, 100000)
        print(f"->entra get_transcription_add_call_sid, {id_unico}")
        
        mensajes = []
        
        current_time = time.time()
        
        continue_Deepgram = True

        
        if "channel" in transcription:
            sentence_transcript = transcription["channel"]["alternatives"][0]["transcript"]
        else:
            sentence_transcript = None

        #Si sentence_transcript tiene algo (no es None), entonces tiene texto transcrito
        if (sentence_transcript):

            if not transcription["speech_final"]:
                last_received_time = current_time
                
            elif last_received_time is not None and transcription["speech_final"]:
                print(f"FINAL: {sentence_transcript}")
                deepgram_live.deregister_handler(deepgram_live.event.TRANSCRIPT_RECEIVED, get_transcription_add_call_sid)

                # Recupera el historial de mensajes de la llamada actual (el call_sid).
                message_history = conversations[call_sid]

                if boss_calling:
                    user_message = {"role": "user", "content": f"[BOSS] {sentence_transcript}"}
                else:
                    user_message = {"role": "user", "content": sentence_transcript}
                
                # Antes de enviarlo a GPT-4 se añade al historial de mensajes porque debe tener tanto lo que se ha dicho ahora como antes para que GPT-4 tenga el contexto completo.
                message_history.append(user_message)

                # Mensaje que le dice "un momento", "espera", etc. para ganar un poco de tiempo mientras procesa la respuesta de GPT y lo pasa a voz (TTS)
                #await send_mp3_to_twilio("static/audio/wait.mp3", call_sid) 

                # Se envía el historial de mensajes (con el actual que se ha transcrito ya añadido) a GPT-4 para que responda a lo que se acaba de decir en la llamada.
                #full_content, finish_reason, gpt_function_arguments, message_history, function_name = await send_msg_gpt(call_sid, message_history)
                await gpt_and_elevenlabs(call_sid, message_history)                
                
                received_handler = deepgram_live.registerHandler(deepgram_live.event.TRANSCRIPT_RECEIVED, get_transcription_add_call_sid)
                print("DeepgramLive Activado")

        print(f"->sale get_transcription_add_call_sid, {id_unico}")

    
    # Añade evento a la escucha en el caso de recibir audio y lo que haya transcrito lo envía a get_transcription_add_call_sid con la transcripción como argumentos.
    received_handler = deepgram_live.registerHandler(deepgram_live.event.TRANSCRIPT_RECEIVED, get_transcription_add_call_sid)

    return deepgram_live
    

# Función que gestiona cuando se cierra la conexión con Deepgram para saber si ha habido algún error o algo.    
async def handle_closing_event(ecode):
    if (ecode != 1000):
        print(f'Connection closed with code {ecode}.')




async def handle_gpt_answer(full_content, finish_reason, gpt_function_arguments, message_history, function_name, call_sid):
    if gpt_function_arguments:
        gpt_arguments = json.loads(gpt_function_arguments)
        more_actions = gpt_arguments.get("more_actions")
        print(f"more_actions antes del while: {more_actions}") 


    if finish_reason == "function_call":
        print("entra en finish_reason")

        message_history = await manage_functions(full_content, finish_reason, gpt_function_arguments, message_history, function_name, call_sid)
        continue_Deepgram = False

        while more_actions == "true":
            print("ESTÁ en more actions")

            full_content, finish_reason, gpt_function_arguments, message_history, function_name = await send_msg_gpt(call_sid, message_history, streaming=False)
            
            print(f"full_content dentro de more_actions: {full_content}")
            print(f"finish_reason dentro de more_actions: {finish_reason}")
            print(f"gpt_function_arguments dentro de more_actions: {gpt_function_arguments}")            
            print(f"function_name dentro de more_actions: {function_name}")                        
            
            if gpt_function_arguments:
                gpt_arguments = json.loads(gpt_function_arguments)
                more_actions = gpt_arguments.get("more_actions").lower()
            else:
                more_actions = "false"
            
            if more_actions == "true":
                message_history = await manage_functions(full_content, finish_reason, gpt_function_arguments, message_history, function_name, call_sid)

            print(f"more_actions EN EL while: {more_actions}") 
            
    print("DESPUÉS de more actions")



async def gpt_and_elevenlabs(call_sid, message_history):

    async def send_msg_gpt(call_sid, message_history):
        print("entra en send_msg_gpt")
        response = openai.ChatCompletion.create(
            model="gpt-4",  # Assuming you are using gpt-4 model. Modify if needed.
            messages=message_history,
            stream=True
        )

        for chunk in response:
            if "content" in chunk["choices"][0]["delta"]:
                content = chunk["choices"][0]["delta"]["content"]
                print(content)
                yield content
                


    audio_stream = generate(
        api_key=elevenlabs_key,
        text=send_msg_gpt(call_sid, message_history),
        voice="Nicole",
        model="eleven_monolingual_v1",
        stream=True
    )
   
    elevenlabs.stream(audio_stream)

    #await tts11AI_stream(elevenlabs_key, message_history, call_sid)                                    
    

    
    



async def manage_inventory(action_gpt, object_name):
    if action_gpt == 'use':
        if object_name == 'Tesla':
            FUNCTIONS.append(FUNCTIONS_TESLA)
        elif object_name == 'Cisco-Phone':
            print("entra en CISCOPHONE")
            for func in CISCOPHONE:
                FUNCTIONS.append(func)
    elif action_gpt == 'drop':
        if object_name == 'CISCOPHONE':
            FUNCTIONS[:] = [d for d in FUNCTIONS if d.get('name') not in [f.get('name') for f in CISCOPHONE]]
        else:
            FUNCTIONS[:] = [d for d in FUNCTIONS if d.get('name') != object_name]
    else:
        print(f"no es ni use ni drop, es {action_gpt}")

    
async def manage_functions(full_content, finish_reason, gpt_function_arguments, message_history, function_name, call_sid):    

    id_unico = random.uniform(1, 100000)
    print(f"--->entra manage_functions, {id_unico}")


    if finish_reason == "function_call":
    
        gpt_arguments[call_sid] = json.loads(gpt_function_arguments)
        
        active_line = gpt_arguments[call_sid].get("call_sid")

        #Función "pasapalabra" para cuando no quiera decir nada GPT.
        if function_name == "do_nothing":
            gpt_message = {"role": "function", "name": "do_nothing", "content": "{\"success\": \"True\"}"}
            message_history.append(gpt_message)

        #Función para pedir usar un objeto (telefono, ipad, etc.)
        if function_name == "actions-with-objects":
            print("entra en actions-with-objects")
            action_gpt = gpt_arguments[call_sid].get("action")
            object_name = gpt_arguments[call_sid].get("objects")
            await manage_inventory(action_gpt, object_name)
            gpt_message = {
                "role": "function",
                "name": f"{function_name}",
                "content": f'{{"success": "True", "object_name": "{object_name}"}}'

            }
            message_history.append(gpt_message)
        

        #Función para colgar la llamada
        if function_name == "hang_up_call":
            hangup_message = gpt_arguments[call_sid].get("hangup_message")
            if not hangup_message:
                hangup_message = "Un momento"

            hangup_sid = gpt_arguments[call_sid].get("hangup_sid")
            success_result = await hang_up_call(hangup_sid, hangup_message)
            if success_result == "True":
                new_scenario = "call hung up"
            else:
                new_scenario = "hang up error"
                
            gpt_message = {
                "role": "function", 
                "name": "hang_up_call", 
                "content": {
                    "success": success_result, 
                    "new_scenario": new_scenario,
                    "active_line": "none"
                }
            }
            message_history.append(gpt_message)

        #Función para poner en espera la llamada
        if function_name == "put_on_hold":
            action_message = gpt_arguments[call_sid].get("action_message")
            if not action_message:
                action_message = "Un momento"
        
            success_result = await hold_on(active_line, action_message)
            if success_result == "True":
                new_scenario = "call on hold"
            else:
                new_scenario = "hold on error"
                
            gpt_message = {
                "role": "function", 
                "name": "put_on_hold", 
                "content": {
                    "success": success_result, 
                    "new_scenario": new_scenario,
                    "active_line": "none"
                }
            }
            message_history.append(gpt_message)


        #Función para transferir la llamada
        if function_name == "transfer_call":
            success_result = await hold_on(active_line, "Un momento")
            
            if success_result == "True":
                transfer_number = gpt_arguments[call_sid].get("number")
                call_message = gpt_arguments[call_sid].get("call_message")
                success_result = await transfer_call(active_line, transfer_number, call_message)
                new_scenario = "calling transfer number"
            else:
                new_scenario = "hold on error"
                
            gpt_message = {
                "role": "function", 
                "name": "transfer_call",
                "content": f'{{"success": "True", "new_scenario": "{new_scenario}","active_line": "none"}}'
            }
            
            message_history.append(gpt_message)

        
        #Función para cancelar la transferencia de una llamada
        if function_name == "cancel_transfer":
            hangup_message = gpt_arguments[call_sid].get("hangup_message")
            if not hangup_message:
                hangup_message = "OK"

            success_result = await hang_up_call(call_sid, hangup_message)
            if success_result:
                previous_number = gpt_arguments[call_sid].get("previous_number")
                success_result = await retrieve(previous_number)
                if success_result:
                    new_scenario = "Transfer canceled"
                else:
                    new_scenario = "Error canceling transfer"
                    
            else:
                new_scenario = "Error hanging up"
            
            gpt_message = {
                "role": "function", 
                "name": "cancel_transfer",
                "content": f'{{"success": "{success_result}", "new_scenario": "{new_scenario}","active_line": "{previous_number}"}}'
            }
            
            message_history.append(gpt_message)
        

    # Aqui finaliza la función send_msg_gpt y devuelve true para que al volver de la función vuelva a activar Deepgram en una conversación con GPT que estaría
    # atendiendo la llamada a quien esté llamando y dando la información que le vaya solicitando.

    print(f"--->sale manage_functions, {id_unico}")
    
    print(message_history)
    
    return message_history


# Corta el texto en trozos más pequeños añadiendo TTS_Break como indicador del corte. 
async def insert_tts_break(text):
    if len(text) > 30:
        # Encuentra el primer caracter de puntuación después del carácter 70
        for i in range(30, len(text)):
            if text[i] in ',;!?.)':
                # Revisa que el siguiente caracter sea un espacio y no un corchete
                if i+2 < len(text) and text[i+1] == ' ' and text[i+2] != '[':
                    # Inserta el tag [TTS_Break] después del espacio
                    text = text[:i+2] + '[TTS_Break] ' + text[i+2:]
                    break
    return text

            

async def hang_up_call(call_sid, action_message):
    print(f"finalizando llamada")
    await tts11AI_stream(elevenlabs_key, action_message, call_sid, chunk_wait_time=8000)                                    
    try:
        call = twilio_client.calls(call_sid).update(twiml=f'<Response><Hangup/></Response>')
        return "True"
    except TwilioRestException as e:
        return "False"



async def hold_on(call_sid, action_message):
    print(f"poniendo en espera")
    await tts11AI_stream(elevenlabs_key, action_message, call_sid, chunk_wait_time=8000)                                        
    try:
        call = twilio_client.calls(call_sid).update(twiml=f'<Response><Enqueue>{call_sid}</Enqueue></Response>')
        return "True"
    except TwilioRestException as e:
        return "False"
   


async def retrieve(previous_number):
    print(f"recuperando llamada")
    try:
        call = twilio_client.calls(previous_number).update(
            twiml=f'<Response><Connect><Stream url="wss://your-domain.example:7777/stream"><Parameter name="retrieve_sid" value="{previous_number}"/></Stream></Connect></Response>'
        )
        return "True"
    except TwilioRestException as e:
        return "False"

    #call = twilio_client.calls(gpt_call_sid).update(twiml=f'<Response><Dial><Queue>{call_sid}</Queue></Dial></Response>')
    



async def transfer_call(active_line, transfer_number, call_message):
    print(f"transfiriendo llamada")
    #await tts11AI_stream(elevenlabs_key, action_message, active_line, chunk_wait_time=8000)                                        
    if transfer_number.startswith("+"):    
        try:
            print(f"llamando a {transfer_number}")
            
            # Create a dictionary with the URL parameters
            params = {
                'call_message': call_message,
                'waiting_sid': active_line
            }
            
            # Convert the parameters to a URL-encoded string
            params_str = urlencode(params)

            # Crea la llamada al jefe y en la url que se aporta para la llamada se añaden los argumentos al final.
            twilio_client.calls.create(url=f"https://your-domain.example:7777/answer?{params_str}",to=f"{transfer_number}",from_="<TWILIO_PHONE_NUMBER>")
        except TwilioRestException as e:
            return "False"
    else:
        try:
            call = twilio_client.calls(active_line).update(twiml=f'<Response><Dial><Queue>{transfer_number}</Queue></Dial></Response>')                            
            return "True"
        except TwilioRestException as e:
            return "False"



async def send_mp3_to_twilio(mp3_file: str, call_sid: str):
    global connected_websockets, twilio_stream

    ws = connected_websockets[call_sid]
    streamSid = twilio_stream[call_sid]['start']['streamSid']

    # Cargar el archivo MP3 con pydub
    audio = AudioSegment.from_mp3(mp3_file)

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
        


def read_role_prompt(file_path, call_sid):
    with open(file_path, "r", encoding='utf-8') as file:
        content = file.read().strip()
        current_time = datetime.now().strftime('%I:%M %p')
        return content.format(call_sid=call_sid, current_time=current_time)



def initialize_role_message(call_sid):
    global conversations, from_call_sid, query_params

    if call_sid not in conversations:
        role_prompt = read_role_prompt(role_file_path, call_sid)
        
        # Se añade el prompt del rol donde indica el rol que hará GPT-4
        conversations[call_sid] = [{"role": "system", "content": role_prompt}]
        


# Función que hace la llamada a la API de OpenAI de GPT, utilizando actualmente la versión gpt-4-1106-preview (GPT-4 Turbo) que
# es la que tiene para funciones de GPT.
async def generate_chat_completion(call_sid, messages, model="gpt-4-1106-preview", temperature=0.5, max_tokens=None, streaming=True):

    print(messages)

    # Si no se indica un tope de tokens a utilizar se asigna que puede utilizar el máximo que GPT permita.
    if max_tokens is not None:
        max_tokens = max_tokens

    # Añade los headers y la api_key para identificarse ante la API de OpenAI.
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {openai_key}",
    }

    # URL a la que enviar las peticiones de la API.
    url = f"https://api.openai.com/v1/chat/completions"

    # Los datos que se envían a la API.
    # Aquí se indica el modelo que utilizar de GPT, y se envían los mensajes en messages que es el historial
    # de mensajes de lo que se ha ido hablando. Y en functions se le envía las funciones que puede utilizar.
    data = {
        # model de GPT a utilizar
        "model": model,

        # los mensajes que se van a enviar a GPT. Aquí se envia todo el historial de mensajes.
        "messages": messages,

        # se inician/explican las funciones que podrá utilizar.
        "functions": FUNCTIONS,

        # maximo de tokens a utilizar
        "max_tokens": max_tokens,

        # temperatura/creatividad de las respuestas
        "temperature": temperature,

        # aunque por defecto ya está en auto se le pone en auto el utilizar las funciones si lo requiere.
        "function_call": "auto",

        # recepción de las respuestas mediante stream de texto
        "stream": True
    }

    async with ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            async for chunk in response.content:
                yield chunk.decode("utf-8")



async def generate_gpt_no_streaming(call_sid, messages, model="gpt-4-1106-preview", temperature=0.5, max_tokens=None):
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        functions=FUNCTIONS,
        function_call="auto"
    )
    return response 
 


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


@app.websocket("/stream")
async def stream(websocket: WebSocket):
    global deepgram_live
    global connected_websockets, twilio_stream, conversations
    
    local_websockets = websocket

    # Recibe el websocket y hace un bucle infinito para estar siempre recibiendo datos.
    await websocket.accept()

    try:
        while True:  # while para mantener la conexión abierta

            while True: #while para ciclo de conversación
                message = await websocket.receive_text()

                # Si en el socket se recibe algo pero no es texto lo ignora y pasa a la siguiente vuelta del bucle.
                if message is None:
                    continue

                # capta los mensajes de data en formato json.
                data = json.loads(message)

                if data['event'] == "start":
                    call_sid = data['start']['callSid']

                    # Por defecto se asume que el jefe no está llamando.
                    boss_calling = False
                
                    print(f"Connected START received, call_sid: {call_sid}")
                   
                    connected_websockets[call_sid] = websocket
                    
                    parameters = data['start']
                    custom_parameters = data['start'].get('customParameters')
                    
                    if custom_parameters:
                        waiting_sid = custom_parameters.get("waiting_sid")
                        retrieve_sid = custom_parameters.get("retrieve_sid")
                        print(f"waitingSID: {waiting_sid}")

                        # Y luego se mira si se está llamando al jefe o si el jefe está llamando.
                        # Si es así, entonces se asigna a True que está llamando para saber que la llamada es con el jefe.
                        num_from = custom_parameters.get("num_from")

                        if num_from == "<BOSS_PHONE_NUMBER>":
                            boss_calling = True
                        
                        num_to = custom_parameters.get("num_to")
                        if num_to == "<BOSS_PHONE_NUMBER>":
                            boss_calling = True

                        for key, value in custom_parameters.items():
                            print(f"key: {key} , value: {value}")                        

                    deepgram_live = await setup_deepgram_sdk(call_sid, boss_calling)

                    stream_sid = data['start']['streamSid']
                    twilio_stream[call_sid] = data
                    
                    if call_sid not in conversations:
                        # Número aleatorio para que diga de manera aleatoria entre la intro-1 a la intro-5 un mensaje de bienvenida en mp3
                        random_number = random.randint(1, 5)
                    
                        if waiting_sid:
                            conversations[call_sid] = conversations[waiting_sid]
                            message_history = conversations[waiting_sid]
                            active_line = {
                                "role": "function",
                                "name": "transfer_call",
                                "content": f'{{"success": "True", "new_scenario": "talk before transfer","active_line": "{call_sid}"}}'
                            }
                        else:
                            initialize_role_message(call_sid)
                            message_history = conversations[call_sid]
                            active_line = {
                                "role": "function",
                                "name": "answer_call",
                                "content": f'{{"success": "True", "new_scenario": "on the phone","active_line": "{call_sid}"}}'
                            }
                        
                        message_history.append(active_line)
                        
                        await send_mp3_to_twilio(f"static/audio/intro-{random_number}.mp3", call_sid)
                    
                    else:
                        if retrieve_sid:
                            conversations[call_sid] = conversations[retrieve_sid]
                            message_history = conversations[retrieve_sid]
                            active_line = {
                                "role": "function",
                                "name": "transfer_call",
                                "content": f'{{"success": "True", "new_scenario": "call retrieved","active_line": "{call_sid}"}}'
                            }
                            message_history.append(active_line)
                            full_content, finish_reason, gpt_function_arguments, message_history, function_name = await send_msg_gpt(call_sid, message_history)
                            await handle_gpt_answer(full_content, finish_reason, gpt_function_arguments, message_history, function_name, call_sid)
                            

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

    # Se muestra en consola si desconecta el socket
    except WebSocketDisconnect:
        #pass
        print("WebSocketDisconnect")

    # Se muestra en consola si hay alguna excepción imprevista
    except Exception as e:
        print(f"error: {str(e)}")

    # Se muestra en consola cuando la función finaliza, se cierra deepgram y se borra la variable del socket con la call_sid
    finally:
        print("Exiting")
        await deepgram_live.finish()
        if connected_websockets.get(call_sid):
            del connected_websockets[call_sid] 



@app.post('/answer')
async def answer(request: Request):
    global from_call_sid, query_params

    # Datos que ha enviado twilio al responder la llamada.
    form_data = await request.form()
    
    # Datos que se han enviado como parámetros adicionales propios a la llamada.
    query_params = request.query_params

    # Imprimir los parámetros de la URL (un poco de debug para ver que está todo bien)
    for param in query_params.keys():
        print(f'URL Param - {param}: {query_params[param]}')

    # Asigna el call_sid de la llamada actual que lo envía twilio la primera vez al responder la llamada.
    call_sid = form_data["CallSid"]

    from_call_sid = query_params.get('call_sid')

    num_from = form_data["From"]
    num_to = form_data["To"]
    
    call_message = query_params.get("call_message")
    waiting_sid = query_params.get("waiting_sid")

    response = VoiceResponse()
    connect = Connect()
    #connect.stream(name=f'{call_sid}', url=f'wss://your-domain.example:7777/stream')
    stream = Stream(url=f'wss://your-domain.example:7777/stream')
    stream.parameter(name='num_from', value=f'{num_from}')
    stream.parameter(name='num_to', value=f'{num_to}')
    
    if call_message:
        stream.parameter(name='call_message', value=f'{call_message}')
        
    if waiting_sid:
        stream.parameter(name='waiting_sid', value=f'{waiting_sid}')    
        
    connect.append(stream)
    response.append(connect)

    return Response(content=str(response), media_type='text/xml')


# inicia la aplicación utilizando uvicorn para que sea en modo seguro y utilice los certificados para https
if __name__ == '__main__':
    number = twilio_client.incoming_phone_numbers.list()[0]
    print(f'Waiting for calls on {number.phone_number}')
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=7777, ssl_certfile='static/sec/cert.pem', ssl_keyfile='static/sec/privkey.pem')
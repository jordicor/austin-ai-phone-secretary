###########
# Flujo de la app: llamada de teléfono entra a twilio y la primera en ejecutarse es la funcíon Answer, de ahí la envia a la función Stream, la cual inicializa otras, entre ellas Deepgram que se quedará a la escucha de recibir audio desde Stream y lo transcribirá.
# Cada vez que transcriba algo se activa la función get_transcription_add_call_sid que recibe la transcripción, de ahí la interpreta, la envía a GPT y recibe la respuesta que también interpreta y pasa a TTS para responder por voz o ejecuta las funciones que haya pedido GPT.
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
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse

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

rol = "austin-3.5"
rol = "secretaria"
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

# Función en la que se inicializa deepgram. Se llama el módulo de deepgram y se le pasa la api key para autentificarse.
# Luego llama a la función de deepgram para las transcripciones en tiempo real tipo streaming y la asigna a deepgram_live,
# a la cual luego se le añade un evento a la escucha para que cada vez que detecte algo lo envíe a la función handle_closing_event.
# Si no puede iniciar la función de transcripción muestra error, y en el caso de que esté la conexión abierta y se cierre el socket
# mostrará el código y la razón.
# De parámetros tiene que añada puntuación a la transcripción (comas, puntos, acentos..), que el lenguaje es en español,
# también se indica el tipo de audio y bitrate (el de twilio), y qué modelo se está utilizando para la transcripciòn.
async def setup_deepgram_sdk(call_sid, boss_calling):
    global received_handler
    deepgram = Deepgram(deepgram_key)

    try:
        #deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'enhanced', 'model' : 'general'})
#noviembre 2023 -- lo comento para poner el nova2        deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'nova', 'model' : 'general'})
        deepgram_live = await deepgram.transcription.live({'punctuate': True, 'interim_results': True, 'language': 'es', 'encoding': 'mulaw', 'sample_rate': 8000, 'tier' : 'nova', 'model' : 'general'})
    except ConnectionClosedError as e:
        print(f'Connection closed with code {e.code} and reason {e.reason}.')
        return None
    except Exception as e:
        print(f'Could not open socket: {e}')
        return None

    # Añade un evento a la escucha en el caso de cerrar el streaming a la escucha.
    deepgram_live.registerHandler(deepgram_live.event.CLOSE, handle_closing_event)
    

    # Función que gestiona la transcripción de audio a voz. Detecta en tiempo real mediante streaming todo lo que se diga y envía contínuamente información.
    # Por lo cual hay que filtrar lo que va recibiendo para saber si ha captado una frase completa que es cuando envía speech_final.
    # Se recibe una línea larga en json en la variable transcription que está recibiendo mediante argumentos de la función.
    # Esta variable con estos datos de la transcripción se reciben desde el handler que está a la escucha todo el rato que ha sido activado en setup_deepgram_sdk , en received_handler = deepgram_live.registerHandler 
    async def get_transcription_add_call_sid(transcription):
        global accumulated_transcript, last_received_time, sentence_transcript, mensajes, deepgram_live, received_handler, connected_websockets
        
        id_unico = random.uniform(1, 100000)
        print(f"->entra get_transcription_add_call_sid, {id_unico}")
        
        mensajes = []
        
        current_time = time.time()
        
        # Primero revisa que exista "channel" en el json porque puede estar enviando otras cosas que no nos interesan.
        # Si existe channel entonces capta lo que se ha transcrito, sino, se asigna a none para que luego no entre
        # a revisar más a fondo que pone en sentence_transcript.
        if "channel" in transcription:
            sentence_transcript = transcription["channel"]["alternatives"][0]["transcript"]
        else:
            sentence_transcript = None

        #Si sentence_transcript tiene algo (no es None), entonces tiene texto transcrito
        if (sentence_transcript):

            # En el json de transcription hay varias secciones, una de ellas es la de speech_final, en la que
            # si aparece significa que ha detectado una frase completa de manera correcta. Si no pone speech_final es que 
            # entonces va enviando en streaming en tiempo real los trozos que va entendiendo que se han dicho
            # pero pueden ir cambiando o ser erróneos. Puede servir para que visualmente se vea como va detectando
            # pero para una llamada por teléfono no es necesario. Así que sólo se procesará cuando sea speech_final.
            # Se asigna la última hora en la que se ha detectado algo porque si detecta speech_final pero sin haber enviado
            # algo antes puede que sólo sea silencio y envia final todo el rato sin parar.
            # También se asigna la hora para que luego pueda comparar entre la última vez recibido speech_final y que pasen 2 segundos.
            # Pero por ahora no se está haciendo.
            if not transcription["speech_final"]:
                last_received_time = current_time
                
            elif last_received_time is not None and transcription["speech_final"]:
                # se asigna la hora que lo ha recibido por si se quiere dar un delay de unos segundos. (no se está haciendo por ahora)
                last_received_time = current_time
                
                # Muestra por consola la transcripción completa que ha detectado y desactiva el evento a la escucha para transcribir
                # para que mientras se está procesando la transcripción no siga escuchando y enviando mensajes.
                # Porque la gente tiene la costumbre de seguir hablando mientras GPT responde o está procesando y se puede hacer una mezcla
                # rara de mensajes. Así que se desactiva la escucha de audio a transcribir y se activa luego al final de procesar lo que ahora ha detectado.
                print(f"FINAL: {sentence_transcript}")
                deepgram_live.deregister_handler(deepgram_live.event.TRANSCRIPT_RECEIVED, get_transcription_add_call_sid)

                # Recupera el historial de mensajes de la llamada actual (el call_sid).
                message_history = conversations[call_sid]

                # Si se detecta el sid del jefe o que esté asignada la variable que está llamando el jefe a Austin (o Austin al jefe)
                # entonces se añade al principio del texto que se enviará a GPT-4 el tag del call_sid y _BOSS para que así lo identifique como tal
                # en el prompt ya se le indica que así le reconocerá.
                # Como cada llamada tiene un call_sid diferente y se comprueba el número que llama y se incluye el call_sid así se evita que alguien intente hacerse pasar por el jefe de algún modo.
                # Se crea la linea que se enviará a GPT-4 en la que se indica lo que se ha transcrito de voz a texto y que es el usuario ha dicho.
                if boss_calling:
                    user_message = {"role": "user", "content": f"[{call_sid}_BOSS] {sentence_transcript}"}
                else:
                    user_message = {"role": "user", "content": sentence_transcript}
                
                # Antes de enviarlo a GPT-4 se añade al historial de mensajes porque debe tener tanto lo que se ha dicho ahora como antes para que GPT-4 tenga el contexto completo.
                message_history.append(user_message)

                # Mensaje que le dice "un momento", "espera", etc. para ganar un poco de tiempo mientras procesa la respuesta de GPT y lo pasa a voz (TTS)
                #await send_mp3_to_twilio("static/audio/wait.mp3", call_sid) 

                # Se envía el historial de mensajes (con el actual que se ha transcrito ya añadido) a GPT-4 para que responda a lo que se acaba de decir en la llamada.
                full_content, finish_reason, gpt_function_arguments, message_history, function_name = await send_msg_gpt(call_sid, message_history)
                
                if gpt_function_arguments:
                    gpt_arguments = json.loads(gpt_function_arguments)
                    more_actions = gpt_arguments.get("more_actions")
                    print(f"more_actions antes del while: {more_actions}") 


                # Si ha finalizado el streaming de texto con motivo function_call entonces se llama la función manage_functions que gestionará las funciones que se están llamando
                # en el texto recibido por streaming. A la vez que se llama la función se asigna a function_response lo que devuelva manage_functions con return, que será
                # el historial de mensajes, que básicamente en ese historial de mensajes se reciben las respuestas de las funciones que se han invocado.
                # Y con esa respuesta de las funciones se hace una segunda llamada a GPT para que sepa el resultado de haber llamado a la función.
                if finish_reason == "function_call":
                    print("entra en finish_reason")
                    # Gestiona las funciones que haya llamado y recoge la respuesta que hayan dado
                    message_history = await manage_functions(full_content, finish_reason, gpt_function_arguments, message_history, function_name, call_sid)
                    continue_Deepgram = False
                    # Se envía a GPT de nuevo mediante send_msg_gpt y se asignan todos esos valores que retornará send_msg_gpt por si pide de nuevo usar otra función recursivamente
                    while more_actions == "True":
                        print("ESTÁ en more actions")
                        # Llama de nuevo a la gestion de funciones por si ha llamado a alguna.
                        full_content, finish_reason, gpt_function_arguments, message_history, function_name = await send_msg_gpt(call_sid, message_history)
                        if gpt_function_arguments:
                            gpt_arguments = json.loads(gpt_function_arguments)
                            more_actions = gpt_arguments.get("more_actions")
                        else:
                            more_actions = "False"
                        
                        if more_actions == "True":
                            message_history = await manage_functions(full_content, finish_reason, gpt_function_arguments, message_history, function_name, call_sid)

                        print(f"more_actions EN EL while: {more_actions}") 
                        
                else:
                    continue_Deepgram = True
                
                print("DESPUÉS de more actions")
                
                # Si después de hacer la llamada a GPT-4 devuelve true significa que lo siguiente que hará es volver a activar la escucha de eventos 
                # de Deepgram para que vaya transcribiendo todo lo que se hable. Si es false es porque tal vez colgará la llamada, la transferirá o que llamará al jefe
                # y en ese caso al llamar al jefe ya se activará una llamada nueva que se responderá en la función answer, la enviará a Connect y ahí activará deepgram de nuevo.
                # Si no se revisa esto, al volver de llamar la función de GPT-4 se activaría 2 veces Deepgram: con la llamada y al volver y encontrar la línea de activar Deepgram.
                if continue_Deepgram:
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
 

# Envía a GPT-4 el historial de mensajes. Lo hace solicitando la respuesta mediante streaming 
# para que pueda captar más rápido la respuesta y enviar el texto troceado más rápidamente a convertir en voz (TTS)
# y de ahí a la persona que esté al teléfono.
async def send_msg_gpt(call_sid, message_history):
    gpt_function_arguments = ""
    function_name = ""
    finish_reason = ""
    content = ""
    full_content = ""
    
    id_unico = random.uniform(1, 100000)
    print(f"-->entra send_msg_gpt, {id_unico}")
    
    
    # con el streaming llega al principio de cada linea con el texto "data:" si es parte de la respuesta JSON
    # pero hay veces que no lo pone para poner "DONE" u otras cosas que no hay que parsear pero que darían error
    # así que si no pone "data:" salta el bucle a la siguiente iteración.
    # Aquí se crea un bucle que va recibiendo cada una de las líneas que va respondiendo GPT-4 que es
    # la respuesta en streaming de texto. La llamada como tal a la API de GPT-4 se está haciendo dentro del
    # mismo bucle con la función generate_chat_completion.
    # Lo que hay dentro de este bucle de esta función es la gestión de la respuesta. Pero la llamada como tal a la API,
    # enviarle el histórico de mensajes y donde se le definen los parámetros, funciones, etc. es en 
    # la función generate_chat_completion a la cual se invoca aquí pero que dentro de la misma tiene los parámetros para GPT.
    async for line in generate_chat_completion(call_sid, message_history):
        #print(line)
        if not line.startswith("data:"):
            continue
        else:
            # el json es a partir del carácter 5 (evitando la palabra "data:")
            # va asignando en cada vuelta del bucle finish_reason
            # hasta que casi en la última si que habrá una razón de fin
            json_data = json.loads(line[5:])
            finish_reason = json_data["choices"][0].get("finish_reason")
            
            # si hay razón de fin de estar recibiendo el streaming y la razón es "stop"
            # significa que ya no hay nada más que recibir así que se sale del bucle.
            if finish_reason == "stop":
                break
            
            # Si finish_reason es function_call significa que ha finalizado de enviar el stream de invocar las funciones de GPT-4.
            # Se añade gpt_function_arguments a full_content porque cuando invoca las funciones de GPT-4
            # primero envía una línea tipo "cabecera" de la función a llamar y luego
            # llegan mediante streaming los argumentos de la función.
            # Con full_content se tiene la cabecera y detectar que ha acabado de recibir el streaming (con finish_reason)
            # se le unen los argumentos que se han ido acumulando en gpt_function_arguments.
            # La variable full_content una vez completa se utiliza para añadirla al historial de mensajes que se han enviado y recibido con GPT
            if finish_reason == "function_call":
                full_content += gpt_function_arguments
                break
            
            # En el json, la primera respuesta (0) y la variable "delta" es donde se reciben
            # las en streaming de texto de GPT-4.
            # El texto llega troceado y hay que irlo acumulando.
            # para las funciones puede venir el valor en [0]["delta"]["name"] o [0]["delta"]["arguments"]
            # por lo cual sólo se capta el valor de ["delta"] y se comprueba después si son los argumentos o no.
            gpt_stream = json_data["choices"][0]["delta"]

            # Si se detecta la palabra "function_call" dentro de la variable gpt_stream
            # significa que está invocando a una de las funciones que se han definido al llamar a GPT
            # Si a la vez que llama a la función tambien pone "content" significa que es la primera línea
            # en la que llama a la función, así que se recoge el nombre de la función y se añade el nombre
            # de la función a full_content que luego se usará para añadirle los argumentos al finalizar.
            # En principio full_content debería estar vacío pero le pongo += por si hay que añadir algo que ponga extra (alguna línea más o algo)
            # siempre y cuando siga siendo "content" además de "function_call)

            gpt_function = gpt_stream.get("function_call")
            new_content = gpt_stream.get("content")

            if gpt_function:
                if gpt_function.get("name"):
                    function_name = gpt_function["name"]
                    full_content += function_name
                
                # Si pone function_call pero no pone "content" entonces es que está enviando los argumentos de las funciones.
                # Se envian en texto troceado (streaming) por lo que hay que irlo agrupando hasta que finalice.
                elif gpt_function.get("arguments"):
                    stream_arguments = gpt_function["arguments"]
                    gpt_function_arguments += stream_arguments
        
            # Si no pone "function_call" pero pone "content" entonces es que está dando una respuesta standard de texto por streaming
            # en este caso el texto siempre vendrá desde [0]["delta"]["content"] por lo que se captará la información directamente desde ahí.
            elif new_content:
                #new_content = json_data["choices"][0]["delta"]["content"]

                # En new_content viene cada vez un trozo de texto por streaming y hay que agruparlo en una variable.
                # Para este caso se utilizan dos variables, una que captará todo el texto al completo que será el que se incluirá en el historial
                # de mensajes. Y otro que se utilizará para detectar cuando pone "[TTS_Break]" lo cual es un indicador para cortar ahí el texto
                # recibido en trozos más pequeños que se enviarán a la función para pasarla a voz (TTS) y que vaya enviando de manera
                # más seguida los trozos y así sea más fluida la conversación sin tener que esperar al texto completo.
                # Pero una vez se ha detectado el tag de TTS_Break hay que vaciarlo para que sólo pida al TTS cada trozo de TTS sin acumular el anterior.
                # Así se tiene el historial completo en full_content para GPT y se va agrupando el stream a trozos y vaciándolo con la variable content.
                full_content += new_content
                content += new_content

                # Llama a función que trocea el texto en trozos más pequeños para que se pueda enviar al TTS de modo más seguido y hacerlo más fluido.
                content = await insert_tts_break(content)

                # Para ir revisando que va respondiendo
                # print(content)
            
                # Si detecta la palabra [TTS_Break] entonces parte en dos la variable "content" buscando donde pone "TTS_Break" como punto de corte,
                # quedándose en tts_content con el primer trozo (0) del corte donde entonces sólo está el texto que ha respondido GPT sin la palabra TTS_Break.
                if '[TTS_Break]' in content:
                    tts_content = content.split('[TTS_Break]')[0]
                    # Si tts_content no está vacío (verificando que no haya error o no haya respondido nada)
                    # se vacía la variable "content" para luego ir recibiendo más texto que enviar al TTS.
                    # Y entonces se envía el texto de tts_content a la función tts11AI_stream para que convierta en voz el texto
                    # el cual desde esa función se llama a otra que enviará a twilio ese texto en audio.
                    if (tts_content):
                        content = content.split('[TTS_Break]')[1]
                        #print(f"tts_content: {tts_content}")

                        # llamada a la función que pasa a voz el texto.
                        await tts11AI_stream(elevenlabs_key, tts_content, call_sid)                                

    # Después de finalizar el bucle de la respuesta de GPT se tiene el contenido completo de lo que ha respondido
    # se crea la línea de lo que ha respondido GPT (assistant)
    gpt_message = {"role": "assistant", "content": full_content}
    
    # y se añade al historial de mensajes que se han ido enviando, para que así GPT sepa toda la conversación
    # tanto los mensajes que envía el usuario como las respuestas que ha ido dando GPT al usuario.
    message_history.append(gpt_message)
    
    # revisando la variable del texto completo
    print(full_content)
    
    print(f"-->sale send_msg_gpt, {id_unico}")

    return full_content, finish_reason, gpt_function_arguments, message_history, function_name

    
async def manage_functions(full_content, finish_reason, gpt_function_arguments, message_history, function_name, call_sid):    

    id_unico = random.uniform(1, 100000)
    print(f"--->entra manage_functions, {id_unico}")


    # Una vez ha salido del bucle de la respuesta de GPT significa que ya se ha recibido un motivo de 
    # finish_reason , en el caso de ser "function_call" significa que estaba llamando a las funciones
    # por lo que se gestiona las llamadas a las funciones de GPT.
    if finish_reason == "function_call":
    
        # Creo una variable con los argumentos que se han incluido al llamar a la función
        # y la variable incluye el call_sid en el caso de que quiera acceder a esos argumentos
        # desde otra llamada con un call_sid diferente pero que ya tenga el call_sid de procedencia como cuando
        # Austin llama al jefe y se aporta ese valor.
        gpt_arguments[call_sid] = json.loads(gpt_function_arguments)
        
        # Dentro de los argumentos uno de ellos es el call_sid de la llamada que quiere manipular.
        # En este caso puede ser el mismo call_sid que la llamada actual o podría ser otro,
        # por ejemplo en el caso de querer recuperar una llamada en espera o colgar una llamada 
        # que tendrán un call_sid diferente de la actual.
        gpt_call_sid = gpt_arguments[call_sid]["call_sid"]

        # Se mira qué función está invocando. 
        # En este caso si está invocando a la función twilio se revisa qué acción quiere hacer.
        if function_name == "do_nothing":
            gpt_message = {"role": "function", "name": "do_nothing", "content": "{\"success\": \"True\"}"}
            message_history.append(gpt_message)
        
        if function_name == "twilio":
            # Se capta qué acción ha indicado en los argumentos de la llamada de la función.
            gpt_action = gpt_arguments[call_sid]["action"]

            action_message = gpt_arguments[call_sid].get("action_message")
            if not action_message:
                action_message = "Un momento"
            
            # Si la accción es "hold_on" primero llama a la función indicada para esto,
            # luego se añade al historial de mensajes con GPT una línea que es lo que habría respondido la función hold_on
            # en la que indica si ha tenido éxito o no al darle a hold (poner en espera).
            # Si es True, todo bien, sino, en el prompt tiene indicado que pida disculpas por tener problemas técnicos
            # con el teléfono y que llamen más tarde y luego que cuelgue.
            # Al crear esa línea y luego añadirla al historial de mensajes se le envía de modo anidado a GPT.
            # Y se pone que devuelva "false" porque en cualquiera de los casos no hace falta que Deepgram se active para trancribir
            # porque si pone la llamada en espera la otra persona está escuchando música de espera y no se escucha lo que dice
            # por lo cual no se puede transcribir nada. Y si da error lo que hará será responder que hay problemas técnicos y colgará.
            # Por ahora siempre le envía "true" o sino lo cambio a mano pero tengo que hacer que recupere el valor de si realmente ha funcionado o no la llamada a la función.
            if gpt_action == "hold_on":
                success_result = await hold_on(gpt_call_sid, action_message)
                gpt_message = {"role": "function", "name": "hold_on", "content": f"{{\"success\": \"{success_result}\"}}"}
                message_history.append(gpt_message)

            # Si la acción es "retrieve" es para recuperar una llamada que esté en espera. Llama a la función que lo hace
            # y luego hace las mismas funcionalidades que con la anterior de hold_on.
            # Se pone return en false porque se redireccionará la llamada al stream de texto donde ahí se iniciará Deepgram.
            elif gpt_action == "retrieve":
                success_result = await hold_on(gpt_call_sid, action_message)
                if success_result == "True":
                    success_result = await retrieve(call_sid, gpt_call_sid)
                gpt_message = {"role": "function", "name": "retrieve", "content": f"{{\"success\": \"{success_result}\"}}"}
                message_history.append(gpt_message)

            # Si la acción es "transfer" es para transferir la llamada.
            # Todavía por pulir si hay que añadir más código.
            elif gpt_action == "transfer":
                success_result = await transfer_call(call_sid, gpt_call_sid, action_message)
                gpt_message = {"role": "function", "name": "transfer", "content": f"{{\"success\": \"{success_result}\"}}"}
                message_history.append(gpt_message)

            elif gpt_action == "hang_up":
                # Si la acción es hang_up llama la función para que cuelgue la llamada con el call_sid indicado.
                # Una vez cuelgue ya no tendrá más contacto con la llamada por lo que no hay que enviar nada a GPT ni iniciar Deepgram después.
                #closing_message = gpt_arguments[call_sid]["closing_message"]
                success_result = await hang_up_call(gpt_call_sid, action_message)
                gpt_message = {"role": "function", "name": "hang_up", "content": f"{{\"success\": \"{success_result}\"}}"}
                message_history.append(gpt_message)


        # Si la función que está llamando es call_boss significa que Austin ha determinado que ya tiene toda la información
        # necesaria de llamada y quiere hablar con su jefe para preguntarle si quiere atender o no la llamada.
        # Toda esta información que ha captado en la llamada la resume indicando los argumentos de la función.
        # Se captan estos argumentos y se llama a la función de generar la llamada al jefe.
        # Se le indica por ahora siempre "true" como que se ha podido llamar exitosamente (podría ser que no si no responde o da error), hay que hacerlo.
        # Y luego se añade esto al historias del mensajes para que GPT entienda que ha hecho la llamada al jefe de manera exitosa (ha atendido) y está esperando
        # que le diga algo.
        # Cuando se descuelgue la llamada por el jefe se activarán las funciones de nueva llamada empezando por la función answer que luego lo llevará a Connect
        # y ahí comprobará si es el jefe poniendo _BOSS delante del texto y entonces Austin interactuará con el jefe teniendo el contexto de las últimas líneas
        # de conversación de esta llamada actual en la que verá que ha escrito la función y sus argumentos y que el jefe ha atendido la llamada.
        # Al final devuelve False porque no quiere ponerse a la escucha el audio para transcribir el audio de esta llamada, se transcribirá la conversacíón con
        # el jefe cuando atienda la llamada y ahí ya se activa Deepgram.
        if function_name == "call_boss":
            args_caller_name = gpt_arguments[call_sid]["caller_name"]        
            args_company = gpt_arguments[call_sid]["company"]        
            args_company_name = gpt_arguments[call_sid]["company_name"]                    
            args_reason_call = gpt_arguments[call_sid]["reason_call"]                               
        
            gpt_message = {"role": "function", "name": "call_boss", "content": "{\"success\": \"True\"}"}
            message_history.append(gpt_message)

            ensure_future(call_boss(args_caller_name, args_company, args_company_name, args_reason_call, gpt_call_sid))
            #await call_boss(args_caller_name, args_company, args_company_name, args_reason_call, gpt_call_sid)

    # Aqui finaliza la función send_msg_gpt y devuelve true para que al volver de la función vuelva a activar Deepgram en una conversación con GPT que estaría
    # atendiendo la llamada a quien esté llamando y dando la información que le vaya solicitando.

    print(f"--->sale manage_functions, {id_unico}")
    
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

            
# Funcion para colgar la llamada mediante el call_sid que le proporcione. Utiliza el cliente de twilio actualizando la llamada del call_Sid que se indique
# y le introduce código twiml que es un código propio de twilio para gestionar las llamadas.
async def hang_up_call(call_sid, action_message):
    print(f"finalizando llamada")
    await tts11AI_stream(elevenlabs_key, action_message, call_sid, chunk_wait_time=8000)                                    
    try:
        call = twilio_client.calls(call_sid).update(twiml=f'<Response><Hangup/></Response>')
        return "True"
    except TwilioRestException as e:
        return "False"


# Funcion para poner en espera la llamada mediante el call_sid que le proporcione. 
# Dentro del código twiml se introduce de nuevo call_sid porque al poner la llamada en espera se puede poner el nombre de la cola
# podría ser cualquier otro nombre, por ejemplo "soporte" para enviar todos a la cola de soporte técnico, pero en este caso
# se utiliza el call_sid para que cada persona en espera tenga su propio nombre de cola de espera que será su call_sid.
async def hold_on(call_sid, action_message):
    print(f"poniendo en espera")
    await tts11AI_stream(elevenlabs_key, action_message, call_sid, chunk_wait_time=8000)                                        
    try:
        call = twilio_client.calls(call_sid).update(twiml=f'<Response><Enqueue>{call_sid}</Enqueue></Response>')
        return "True"
    except TwilioRestException as e:
        return "False"
   

# Función para recuperar una llamada que está en espera. 
# La llamada que está en espera que quiere recuperar es otra persona que está "en la otra línea" esperando mientras se habla con el jefe.
# Esta llamada es la que anteriormente había llamado y está esperando si le pasan con el jefe o no.
# Cuando se pone en espera la conexión de sockets se desconecta del stream de texto porque ya está en otro sitio esa llamada (esperando, escuchando música)
# y no se recibe nada. Al redireccionarlo de nuevo al stream lo que hace es sacarlo de la espera y volver a conectar con el stream para seguir hablando.
# Es como darle al botón de la llamada que está en la otra línea y volver a hablar con esa persona.
async def retrieve(call_sid, gpt_call_sid):
    print(f"recuperando llamada")
    try:
        call = twilio_client.calls(gpt_call_sid).update(
            twiml=f'<Response><Connect><Stream url="wss://your-domain.example:7777/stream"><Parameter name="retrieved" value="True"/></Stream></Connect></Response>'
        )
        return "True"
    except TwilioRestException as e:
        return "False"

    #call = twilio_client.calls(gpt_call_sid).update(twiml=f'<Response><Dial><Queue>{call_sid}</Queue></Dial></Response>')
    

# Función para transferir la llamada. Lo que hace es actualizar la llamada en curso para que haga una llamada a la cola con el nombre del call_sid de la llamada anterior
# que actualmente es el argumento recibido de gpt_call_sid, así al llamar a esa cola se pone en contacto con la persona que está en espera.
# Al ser esta llamada en curso la del jefe y se redirecciona a que llame a la cola entonces lo que hace es transferirla y que hable con quien estaba en espera.
async def transfer_call(call_sid, gpt_call_sid, action_message):
    print(f"transfiriendo llamada")
    await tts11AI_stream(elevenlabs_key, action_message, call_sid, chunk_wait_time=8000)                                        
    try:
        call = twilio_client.calls(call_sid).update(twiml=f'<Response><Dial><Queue>{gpt_call_sid}</Queue></Dial></Response>')                            
        return "True"
    except TwilioRestException as e:
        return "False"

# Función para llamar el jefe, aquí recibe mediante argumentos la información de la llamada, pero por ahora realmente no se utilizan
# porque el propio GPT ya sabe interpretarlos cuando atienda la llamada y se le aporten las últimas líneas de la conversación en la que
# habrá indicado estos datos.
# Lo que si que se utiliza es el call_sid que cuando se atienda la llamada se verificará si hay un call_sid enviado por parámetros y 
# si es así se entiende que viene esa llamada de otra anterior (esta), y usará ese call_sid como from_call_sid.
async def call_boss(args_caller_name, args_company, args_company_name, args_reason_call, call_sid):
    print(f"llamando al jefe")
    
    # Create a dictionary with the URL parameters
    params = {
        'callingTo': 'Boss',
        'caller_name': args_caller_name,
        'company': args_company,
        'company_name': args_company_name,
        'reason_call': args_reason_call,
        'call_sid': call_sid
    }
    
    # Convert the parameters to a URL-encoded string
    params_str = urlencode(params)

    # Crea la llamada al jefe y en la url que se aporta para la llamada se añaden los argumentos al final.
    call_boss = twilio_client.calls.create(
        #machine_detection='Enable',
        url=f"https://your-domain.example:7777/answer?{params_str}",
        to="<BOSS_PHONE_NUMBER>",
        #to="<ACERTING_PHONE_NUMBER>", #num de Acerting (Dalacodev)
        from_="<TWILIO_PHONE_NUMBER>"
    )
   

# Función que envía un MP3 a twilio.
# Esta función es para enviar audios que siempre serán los mismos como por ejemplo mensajes de "un momento", 
# la intro de "Hola en qué puedo ayudarte", etc. para que así no haya que generarlos cada vez con el TTS ni con GPT.
# Lo que hace es convertir el MP3 al formato para Twilio (mulaw, 8000, etc..) y luego lo envía igual que con los
# mensajes generados dinámicamente mediante la función send_audio_to_twilio que enviará en base64 el audio a twilio.
async def send_mp3_to_twilio(mp3_file: str, call_sid: str):
    global connected_websockets, twilio_stream

    # Se conecta a los sockets de la llamada con el call_sid indicado para saber a qué sockets enviar el audio
    # y se capta el valor del streamSid que se ha asignado de esa llamada con ese call_sid porque al enviar
    # por streaming en base64 el audio hay que indicar a twilio cuál es el streamSid que recibe el audio.
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
        

# Lee el archivo .txt del rol (prompt) para GPT.
# En el prompt está la variable call_sid que la interpreta para cambiar 
# call_sid por los números y letras que es realmente la call_sid.        
def read_role_prompt(file_path, call_sid):
    with open(file_path, "r", encoding='utf-8') as file:
        content = file.read().strip()
        return content.format(call_sid=call_sid)


# Función para inicializar el mensaje del rol que hará GPT-4
def initialize_role_message(call_sid):
    global conversations, from_call_sid, query_params

    # Comprobamos si el call_sid de la llamada actual ya tiene el historial de conversaciones
    # si no está, inicia historial de conversaciones del call_sid actual y el rol de GPT-4 el cual 
    # es la primera linea del historial de mensajes (el "system" para el prompt de GPT-4)
    if call_sid not in conversations:
        role_prompt = read_role_prompt(role_file_path, call_sid)
        
        if query_params:
            calling_boss_prompt = f"En esta llamada estás hablando con tu jefe, la persona que llama es {query_params['caller_name']}, "
            
            if query_params["company"] == "True":
                calling_boss_prompt += f" nombre de empresa: {query_params['company_name']}, "
            
            calling_boss_prompt += f"motivo de la llamada: {query_params['reason_call']}. El Call SID de la persona en espera (from_call_sid) es: {from_call_sid}. El Call SID con tu jefe es: {call_sid}. Espera a que tu jefe hable al responder la llamada y dile si quiere atender la llamada. Continúa preguntándole hasta que sepas qué hacer con la llamada."

            role_prompt += calling_boss_prompt

        # Si existe la variable from_call_sid es porque la llamada ha sido recibida desde una llamada anterior que le ha pasado argumentos
        # y uno de los argumentos es la procedencia del call_sid de la llamada anterior. Lo cual significa que se ha invocado call_boss
        # y es Austin que está llamando a su jefe, por lo tanto se le da contexto de las 5 líneas anteriores de la conversacion 
        # de la que procede la llamada en la que debe de haber indicado el nombre, motivo de llamada, etc.
        # Así GPT-4 podrá hablar con su jefe y decirle qué es lo que quiere la otra persona e interactuar con el jefe.
        #if from_call_sid:
        #    last_lines = "\n".join([str(item) for item in conversations[from_call_sid][-3:]])
        #    role_prompt += last_lines

        # Se añade el prompt del rol donde indica el rol que hará GPT-4
        conversations[call_sid] = [{"role": "system", "content": role_prompt}]


# Función que hace la llamada a la API de OpenAI de GPT, utilizando actualmente la versión GPT-4-0613 que
# es la que tiene para funciones de GPT.
async def generate_chat_completion(call_sid, messages, model="gpt-4-1106-preview", temperature=0.5, max_tokens=None):

    print(messages)

    # En los argumentos que definen la función ya se indica valor por defecto de la temperatura, pero
    # mantengo esto por si quiero luego que tenga valores aleatorios de la temperatura del modo 
    # en el que responderá GPT (más creativo o menos) según la temperatura.
    if temperature is None:
        temperature = random.uniform(0.4, 0.5)

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
        "functions": [
            {
                "name": "twilio",
                "description": "Manage twilio calls",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string","description": "Action that you want to do (hold_on, retrieve, transfer, hang_up)"},
                        "action_message": {"type": "string","description": "message to say to the caller before doing the action"},
                        "more_actions": {"type": "string", "enum": ["True", "False"], "description": "return True if you will call more actions"},
                        "call_sid": {"type": "string", "description": "the Call SID"},
                        "success": {"type": "string", "enum": ["True", "False"]},                        
                    },
                    "required": ["action","more_actions","call_sid"],
                },
            },
            {
                "name": "call_boss",
                "description": "Function to call your boss and know if wants to attent the call or not",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "caller_name": {"type": "string","description": "Name of the caller"},
                        "company": {"type": "string", "enum": ["True", "False"]},
                        "company_name": {"type": "string", "description": "If it's an individual return n/a, if it's a company return the company name"},
                        "reason_call": {"type": "string", "description": "Reason and detail for the call"},
                        "more_actions": {"type": "string", "enum": ["True", "False"], "description": "return True if you will call more actions"},
                        "call_sid": {"type": "string", "description": "the Call SID"},
                        "success": {"type": "string", "enum": ["True", "False"]},                        
                    },
                    "required": ["caller_name","company","company_name","reason_call","more_actions","call_sid"],
                },
            },
            {
                "name": "do_nothing",
                "description": "Function when you have nothing to do (waiting for your boss, etc.)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "more_actions": {"type": "string",  "enum": ["True", "False"]},
                    },
                    "required": ["more_actions"],
                },
            },
        ],

        # maximo de tokens a utilizar
        "max_tokens": max_tokens,
        
        # temperatura/creatividad de las respuestas
        "temperature": temperature,
        
        # aunque por defecto ya está en auto se le pone en auto el utilizar las funciones si lo requiere.
        "function_call" : "auto",
        
        # recepción de las respuestas mediante stream de texto
        "stream": True
    }

    # ClientSession es un cliente http asíncrono, utilizando este cliente http crea una sessión
    # en la que enviará por http los datos que se han indicado antes.
    # En session.post está enviando a la url de Openai los headers que se han definido antes
    # para identificarse y se envían los datos en json de data que se han definido antes
    # (los mensajes y las funciones) y a la vez que está haciendo la llamada está recibiendo la respuesta
    # http de la cual hace un bucle de cada trozo de respuesta en streaming y lo va devolviendo en utf-8.
    async with ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            async for chunk in response.content:
                yield chunk.decode("utf-8")
 

# Función para enviar audio por streaming a Twilio cuando la llamada se ha establecido mediante Connect
# la cual permite recibir en estado puro el audio de la otra parte y también enviar nuestro propio audio.
# Para enviar el audio a twilio requiere que sea en un formato muy específico (mulaw, 8000) 
# ya se hace la conversión en tts11AI_stream según llega el streaming de audio de Elevenlabs el cual es MP3
# luego esta función con el audio ya en mulaw lo codifica en base64 y lo envía al socket que tiene abierto
# al haber conectado la llamada por stream con Connect.
async def send_audio_to_twilio(ws: WebSocket, chunk: bytes, streamSid: str):
    media_data = {
        "event": "media",
        "streamSid": streamSid,
        "media": {
            "payload": base64.b64encode(chunk).decode("utf-8")
        }
    }
    await ws.send_json(media_data)
    
# Se envía este evento "mark" cuando se ha acabado de enviar media a twilio para saber que se ha finalizado el envío.
# Sin utilizar por ahora.
async def send_mark_to_twilio(ws: WebSocket, streamSid: str):
    media_data = {
        "event": "mark",
        "streamSid": streamSid,
        "mark": {
            "name": "TTS_Audio"
        }
    }
    await ws.send_json(media_data)

# En el caso de tener que transcribir texto a voz que no permita signos raros o emojis.
# Para evitar que diga cosas raras y también para evitar intentos de inyección de código.
def filter_text(text):
    allowed_characters = (string.ascii_letters + string.digits + string.whitespace +
                          string.punctuation + "áéíóúÁÉÍÓÚüÜñÑ")
    filtered_text = ''.join(c for c in text if c in allowed_characters)
    return filtered_text


# Función para llamar la API de Elevenlabs (texto a voz) que produce audio de muy alta calidad y muy natural.
# Los parámetros envían la id de la voz que puede ser un ID de una voz creada por uno mismo entrada con audio de alguien
# o el id de otras voces que existen ya predeterminadas. En stability indica como cuánto varía la voz al pasar el texto a voz.
# Valores muy altos lo hacen muy robótico y muy bajos pueden ser muy imprevisibles, pero si el texto es muy largo hay que poner más baja la stability.
# Similarity es para cuánto debe parecerse la voz a la voz con la que se ha entrenado.
# En este caso la función se le solicita que envíe la respuesta de audio generada mediante streaming para que sea más rápida la respuesta
# y haya menos delays en la llamada. El audio es en MP3 así que se tiene que convertir al formato de twilio mulaw y 8000 de bitrate.
#async def tts11AI_stream(key: str, text: str, voice_id: str = '9MuZVz9czdPipoZ12F8t', stability: float = 0.59, similarity_boost: float = 0.99):
#async def tts11AI_stream(key: str, text: str, call_sid, voice_id: str = 'ErXwobaYiN019PkySvjV', stability: float = 0.59, similarity_boost: float = 0.99, chunk_wait_time: int = 16000):
async def tts11AI_stream(key: str, text: str, call_sid, voice_id: str = 'ErXwobaYiN019PkySvjV', stability: float = 0.59, similarity_boost: float = 0.99, chunk_wait_time: int = 16000):
    global connected_websockets, twilio_stream
    
    id_unico = random.uniform(1, 100000)
    print(f"** entra tts11AI_stream, {id_unico}")
    
    
    # Se inician los sockets a los que se enviará el audio de respuesta del TTS, requiere también el streamSid.
    # Se revisa que los sockets existan para esa call_sid porque si se hubiera finalizado/cortado la llamada y ya no estuviera activa.
    ws = connected_websockets.get(call_sid)
    if ws is not None:  # Si ws no es None, significa que call_sid existe
        streamSid = twilio_stream.get(call_sid)
        if streamSid is not None:
            streamSid = streamSid['start']['streamSid']
        else:
            return  # Si no existe 'call_sid' en 'twilio_stream', retorna
    else:
        return  # Si no existe 'call_sid' en 'connected_websockets', retorna


    # URL a la que se hará la petición de la API
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?optimize_streaming_latency=3"

    # Cabeceras de la llamada HTTP que servirá para autentificarse con la api_key
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key
    }

    # Datos que se envian a la API, se indican los valores de estabilidad, similaridad y el texto que se quiere pasar a voz.
    # También se indica que sea el modelo eleven_multilingual_v1 que es para que genere las voces en otros idiomas diferentes del inglés.
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost
        }
    }

    # Se inicia variable para captar los bytes del MP3 que se recibirá por streaming
    # y se crea una sesión de http en la que se envía mediante post a la url indicada
    # los valores en json de data y el header. Recibe la respuesta y hace un bucle
    # de cada línea que vaya recibiendo en streaming del audio en mp3.
    # Lo va acumulando en trozos de 512 bytes para enviarlos en streaming a twilio.
    audio_mp3 = io.BytesIO()
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            async for chunk in response.content.iter_chunked(512):
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

    # Enviar el audio por stream a Twilio en trozos de 512 
    CHUNK_SIZE = 512

    chunk_duration = CHUNK_SIZE / chunk_wait_time  # Cada chunk dura 0.064 segundos, se divide entre 16000 y no entre 8000 que es el bitrate para que espere un poco menos mientras se genera el TTS y se encadenen mejor.

    total_duration = 0  # Inicializa la duración total en 0
    
    for i in range(0, len(audio_data_mulaw), CHUNK_SIZE):
        chunk = audio_data_mulaw[i:i+CHUNK_SIZE]
        await send_audio_to_twilio(ws, chunk, streamSid)
        # Suma la duración del chunk a la duración total
        total_duration += chunk_duration

    # Ahora total_duration tiene el tiempo total de duración del audio enviado.
    # Puedes usar asyncio.sleep para esperar esa cantidad de tiempo:
    await asyncio.sleep(total_duration)
    print(f"** sale tts11AI_stream, {id_unico}")
    
        


# Función que gestiona el stream de voz de la llamada. Aquí se recibe todo lo que se habla desde
# la persona que está llamando y se puede enviar audio también. Se recibe mediante sockets wss y
# la comunicación es bidireccional en la que se puede entonces gestionar más rápido lo que se recibe.
# No sería necesario en el caso de usar gather de twilio pero no es lo suficientemente bueno y de este
# modo se puede usar un STT (voz a texto) y de ahí enviar a GPT y luego a TTS (texto a voz).
@app.websocket("/stream")
async def stream(websocket: WebSocket):
    global deepgram_live
    global connected_websockets, twilio_stream, conversations
    
    # Se asignan los websockets con el call_sid de esta llamada para
    # que se pueda acceder a diferentes websockets con diferente call_sid
    # en el caso de querer gestionarlos desde otras llamadas paralelas.
    #connected_websockets[call_sid] = websocket
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

                # Si en el json la sección data['event'] es "start" significa que se está iniciando la conexión del stream de voz
                # esto sólo ocurre una vez al establecerse la conexión. Por lo cual se aprovecha para inicializar variables 
                # que se utilizarán en la conversación.
                if data['event'] == "start":
                    call_sid = data['start']['callSid']

                    # Por defecto se asume que el jefe no está llamando.
                    boss_calling = False
                
                    print(f"Connected START received, call_sid: {call_sid}")
                   
                    connected_websockets[call_sid] = websocket
                    
                    parameters = data['start']
                    custom_parameters = data['start'].get('customParameters')
                    
                    if custom_parameters:
                        retrieved = custom_parameters.get("retrieved")


                        # Y luego se mira si se está llamando al jefe o si el jefe está llamando.
                        # Si es así, entonces se asigna a True que está llamando para saber que la llamada es con el jefe.
                        num_from = custom_parameters.get("num_from")

                        if num_from == "<BOSS_PHONE_NUMBER>":
                            boss_calling = True
                        
                        num_to = custom_parameters.get("num_to")
                        if num_to == "<BOSS_PHONE_NUMBER>":
                            boss_calling = True

                        
                        if retrieved == "True":
                            print("sip, retrieved")


                        for key, value in custom_parameters.items():
                            print(f"key: {key} , value: {value}")                        


                    # Se inicia deepgram que será el que transcriba de voz a texto
                    deepgram_live = await setup_deepgram_sdk(call_sid, boss_calling)

                    
                    # twilio_stream con el call_sid para tener los datos de la sesión de esta call_sid 
                    # y stream_sid porque se utilizará luego para enviar audio al stream_sid que se indique.
                    stream_sid = data['start']['streamSid']
                    twilio_stream[call_sid] = data
                    
                    # Revisa que call_sid no exista para dar el mensaje de bienvenida porque, aunque la conexión al stream sólo se realiza
                    # una vez y luego va llegando la info, si que se accede al stream más de una vez, por ejemplo si se pone en espera la
                    # llamada y luego se recupera. En ese caso se desconecta del stream y luego se conecta de nuevo y daría start al conectar
                    # pero no tiene que poner la intro porque ya había una conversación en curso.
                    if call_sid not in conversations:
                        # Número aleatorio para que diga de manera aleatoria entre la intro-1 a la intro-5 un mensaje de bienvenida en mp3
                        random_number = random.randint(1, 5)
                    
                        initialize_role_message(call_sid)
                        await send_mp3_to_twilio(f"static/audio/intro-{random_number}.mp3", call_sid)

                # Si el evento es "media" significa que ya ha conectado y que lo que está enviando es media (audio) en base64 en tiempo real, así que
                # se captan los datos, se decodifican de base64 y se envían a deepgram que está a la escucha y así todo lo que llegue de audio lo va transcribiendo y luego
                # desde la función que llama deepgram ahí también llama a las otras funciones de GPT, TTS, etc.
                if data['event'] == "media":
                    audio = base64.b64decode(data['media']['payload'])
                    if data['media']['track'] == 'inbound':
                        deepgram_live.send(audio)

                # Si el evento es "stop" o "mark" se sale del bucle porque significa que ha finalizado el stream actual de envió de audio 
                # pero seguiría a la espera del bucle que hay por encima de este para mantener la conexión activa y si vuelve a haber audio y se recibe
                # audio entonces entraría de nuevo en este bucle para procesar el audio que se recibe y enviarlo a deepgram.
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


# Funcion que responde cuando hay una llamada al número de twilio.
# En twilio está configurado que al recibir una llamada que vaya a la URL
# del servidor y a esta ruta. Actualmente es https://your-domain.example:7777/answer
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

    # En este caso los parámetros que se reciben son como argumentos extra al llamar a la URL y que pueden
    # estar o no. No son los de twilio sino que son propios.
    # En el caso de existir call_sid en query_params es que se están enviando desde la función call_boss y
    # le está indicando el call_sid de procedencia por si luego quiere volver a recuperar la llamada, colgar o transferir.
    # Así que se asigna from_call_sid ese call_sid que se está pasando.
    from_call_sid = query_params.get('call_sid')

    num_from = form_data["From"]
    num_to = form_data["To"]

    # Una vez ha respondido a la llamada se redirecciona hacia una conexión con Connect que será por stream
    # y se podrá captar la voz en tiempo real y actuar sobre ella.
    # Existe la función gather de twilio pero funciona FATAL para reconocimiento de voz en español
    # siendo además más lenta porque no es por streaming y hace que haya más delay en las interacciones con GPT.
    # Es más conveniente tener transcripción de voz en tiempo real y streaming para poder actuar y enviar más rápido a GPT.
    # Aún así deepgram no es tan bueno transcribiendo en tiempo real como Whisper sin streaming pero tarda más,
    # por lo que se podrían mirar otras opciones más adelante como Whisper JAX que es mucho más rápido.
    # Este modo de redireccionar al stream es dando la respuesta en la propia función añadiendo voiceresponse(), connect(), etc.
    # y luego añadirlo todo para darlo como respuesta en xml el return. Cada llamada a voiceresponse() , connect() es como poner <response><connect>, etc.
    response = VoiceResponse()
    connect = Connect()
    #connect.stream(name=f'{call_sid}', url=f'wss://your-domain.example:7777/stream')
    stream = Stream(url=f'wss://your-domain.example:7777/stream')
    stream.parameter(name='num_from', value=f'{num_from}')
    stream.parameter(name='num_to', value=f'{num_to}')
    connect.append(stream)
    response.append(connect)

    return Response(content=str(response), media_type='text/xml')


# inicia la aplicación utilizando uvicorn para que sea en modo seguro y utilice los certificados para https
if __name__ == '__main__':
    number = twilio_client.incoming_phone_numbers.list()[0]
    print(f'Waiting for calls on {number.phone_number}')
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=7777, ssl_certfile='static/sec/cert.pem', ssl_keyfile='static/sec/privkey.pem')
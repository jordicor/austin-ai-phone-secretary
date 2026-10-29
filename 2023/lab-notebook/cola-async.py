import re
import asyncio
import random

texto_original = "El pez vela[TTS_Break-1654526540] es considerado el pez más rápido del mundo[TTS_Break-1654526544]. Puede alcanzar velocidades de hasta 68 millas por hora (110 km/h)[TTS_Break-1654526548]. Este pez es conocido por su gran aleta dorsal y su cuerpo delgado y aerodinámico[TTS_Break-1654526552][Mark-23423412313][TTS_Break-1654526556]."

async def simular_servidor(timestamp, texto, mensajes_respuesta_dict):
    await asyncio.sleep(random.uniform(2, 10))
    texto_reverso = texto[::-1]
    mensajes_respuesta_dict[timestamp] = texto_reverso

def mostrar_mensaje(mensaje):
    print(mensaje)

async def procesar_texto(texto_original, cola_inicial):
    split_text = re.split(r'\[TTS_Break-(\d+)\]', texto_original)

    for i in range(0, len(split_text) - 1, 2):
        timestamp = int(split_text[i + 1])
        text = split_text[i]
        await cola_inicial.put((timestamp, text))

async def procesar_y_mostrar_respuestas(cola_inicial, mensajes_respuesta_dict):
    while not cola_inicial.empty():
        siguiente_ts, text = await cola_inicial.get()

        task = asyncio.create_task(simular_servidor(siguiente_ts, text, mensajes_respuesta_dict))

        while siguiente_ts not in mensajes_respuesta_dict:
            await asyncio.sleep(0.1)

        mensaje = mensajes_respuesta_dict[siguiente_ts]
        mostrar_mensaje(mensaje)

        await task

async def main():
    mensajes_respuesta_dict = {}
    cola_inicial = asyncio.PriorityQueue()

    await procesar_texto(texto_original, cola_inicial)
    await procesar_y_mostrar_respuestas(cola_inicial, mensajes_respuesta_dict)

asyncio.run(main())

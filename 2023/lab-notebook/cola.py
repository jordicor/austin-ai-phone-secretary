import re
import threading
import time
from queue import PriorityQueue, Queue

texto_original = "El pez vela[TTS_Break-1654526540] es considerado el pez más rápido del mundo[TTS_Break-1654526544]. Puede alcanzar velocidades de hasta 68 millas por hora (110 km/h)[TTS_Break-1654526548]. Este pez es conocido por su gran aleta dorsal y su cuerpo delgado y aerodinámico[TTS_Break-1654526552]."


def recibir_mensaje():
    time.sleep(7)
    texto_procesado = "Este pez es conocido por su gran aleta dorsal y su cuerpo delgado y aerodinámico[TTS_Break-1654526552]"
    return texto_procesado

def recibir_mensaje_2():
    time.sleep(1)
    texto_procesado_2 = ". Puede alcanzar velocidades de hasta 68 millas por hora (110 km/h)[TTS_Break-1654526548]"
    return texto_procesado_2

def recibir_mensaje_3():
    time.sleep(4)
    texto_procesado_3 = ".El pez vela[TTS_Break-1654526540]"
    return texto_procesado_3

def recibir_mensaje_4():
    time.sleep(2)
    texto_procesado_4 = ".es considerado el pez más rápido del mundo[TTS_Break-1654526544]    "
    return texto_procesado_4
    


def mostrar_mensaje(mensaje):
    print(mensaje)


def procesar_texto(mensajes_queue):
    split_text = re.split(r'\[TTS_Break-(\d+)\]', texto_original)

    priority_queue = PriorityQueue()

    for i in range(0, len(split_text) - 1, 2):
        timestamp = int(split_text[i + 1])
        text = split_text[i]
        priority_queue.put((timestamp, text))

    mensajes_dict = {}

    while not priority_queue.empty():
        siguiente_ts, _ = priority_queue.get()

        while siguiente_ts not in mensajes_dict:
            try:
                ts, mensaje = mensajes_queue.get(timeout=1)
                mensajes_dict[ts] = mensaje
            except:
                pass

        mostrar_mensaje(mensajes_dict[siguiente_ts])


def recibir_y_procesar_mensaje(funcion_recibir_mensaje, mensajes_queue):
    texto_procesado = funcion_recibir_mensaje()
    split_text_procesado = re.split(r'\[TTS_Break-(\d+)\]', texto_procesado)

    for i in range(0, len(split_text_procesado) - 1, 2):
        timestamp = int(split_text_procesado[i + 1])
        text = split_text_procesado[i]
        mensajes_queue.put((timestamp, text))


mensajes_queue = Queue()

t1 = threading.Thread(target=recibir_y_procesar_mensaje, args=[recibir_mensaje, mensajes_queue])
t1.start()

t2 = threading.Thread(target=recibir_y_procesar_mensaje, args=[recibir_mensaje_2, mensajes_queue])
t2.start()

t4 = threading.Thread(target=recibir_y_procesar_mensaje, args=[recibir_mensaje_3, mensajes_queue])
t4.start()

t5 = threading.Thread(target=recibir_y_procesar_mensaje, args=[recibir_mensaje_4, mensajes_queue])
t5.start()


t3 = threading.Thread(target=procesar_texto, args=[mensajes_queue])
t3.start()

t1.join()
t2.join()
t3.join()
t4.join()
t5.join()
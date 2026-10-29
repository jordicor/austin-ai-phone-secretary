import re
from queue import PriorityQueue
import threading

texto_original = "El pez vela[TTS_Break-1654526540] es considerado el pez más rápido del mundo[TTS_Break-1654526544]. Puede alcanzar velocidades de hasta 68 millas por hora (110 km/h)[TTS_Break-1654526548]. Este pez es conocido por su gran aleta dorsal y su cuerpo delgado y aerodinámico[TTS_Break-1654526552]."

texto_procesado_1 = "Puede alcanzar velocidades de hasta 68 millas por hora (110 km/h)[TTS_Break-1654526548]"

texto_procesado_2 = "Este pez es conocido por su gran aleta dorsal y su cuerpo delgado y aerodinámico[TTS_Break-1654526552].es considerado el pez más rápido del mundo[TTS_Break-1654526544].El pez vela[TTS_Break-1654526540]"

cola_prioridad = PriorityQueue()
condition = threading.Condition()
esperando_elementos = 2

def procesar_texto(texto):
    global esperando_elementos
    with condition:
        segmentos = re.split(r'(\[TTS_Break-\d+\])', texto)
        for i in range(0, len(segmentos)-1, 2):
            texto, marca_tiempo = segmentos[i], segmentos[i+1]
            timestamp = int(re.search(r'\d+', marca_tiempo).group())
            cola_prioridad.put((timestamp, texto))
        esperando_elementos -= 1
        condition.notify_all()
        print(segmentos)

def imprimir_texto_ordenado():
    texto_ordenado = ""
    ultimo_timestamp = -1
    while True:
        with condition:
            while (cola_prioridad.empty() or cola_prioridad.queue[0][0] != ultimo_timestamp + 1) and esperando_elementos > 0:
                condition.wait()
            if not cola_prioridad.empty() and cola_prioridad.queue[0][0] == ultimo_timestamp + 1:
                timestamp, segmento = cola_prioridad.get()
                texto_ordenado += segmento
                ultimo_timestamp = timestamp
                condition.notify_all()
            else:
                break
    print(texto_ordenado)

# Temporizadores para enviar texto_procesado_1 y texto_procesado_2 a procesar_texto después de 1 y 5 segundos respectivamente

timer1 = threading.Timer(1, procesar_texto, args=[texto_procesado_1])
timer2 = threading.Timer(5, procesar_texto, args=[texto_procesado_2])

# Hilo para imprimir el texto ordenado
imprimir_hilo = threading.Thread(target=imprimir_texto_ordenado)

timer1.start()
timer2.start()
imprimir_hilo.start()

timer1.join()
timer2.join()
imprimir_hilo.join()
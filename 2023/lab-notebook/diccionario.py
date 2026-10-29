import time

TTS_Index = {}

def add_to_TTS_index(text):
    if '[TTS_Break]' in text:
        content = text.split('[TTS_Break]')[0]
        timestamp = int(time.time())
        TTS_Index[timestamp] = content

text = "Los cinco países con los castillos más bonitos son[TTS_Break]"
add_to_TTS_index(text)

print(TTS_Index)

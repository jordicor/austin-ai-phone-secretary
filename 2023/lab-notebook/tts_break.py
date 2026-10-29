def insert_tts_break(text):
    if len(text) > 70:
        # Encuentra el primer caracter de puntuación después del carácter 70
        for i in range(70, len(text)):
            if text[i] in ',;!?.':
                # Revisa que el siguiente caracter sea un espacio y no un corchete
                if i+2 < len(text) and text[i+1] == ' ' and text[i+2] != '[':
                    # Inserta el tag [TTS_Break] después del espacio
                    text = text[:i+2] + '[TTS_Break] ' + text[i+2:]
                    break
    return text

# Prueba de la función
texto = "Buenos días, Pepe. ¿Podría indicarme, por favor, el motivo de su llamada? ¿"
content = insert_tts_break(texto)

if '[TTS_Break]' in content:
    tts_content = content.split('[TTS_Break]')[0]
    if (tts_content):
        content = content.split('[TTS_Break]')[1]
        print(f"tts_content: {tts_content}")
        print(f"content: {content}")  

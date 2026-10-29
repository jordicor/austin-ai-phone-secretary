import sys
import os
from pydub import AudioSegment
import numpy as np

def mulaw_encode(audio, mu=255):
    audio = np.clip(audio, -1, 1)
    audio = np.sign(audio) * (np.log(1 + mu * np.abs(audio)) / np.log(1 + mu))
    return ((audio + 1) / 2 * mu).astype(np.int8)

def convert_mp3_to_mulaw(input_file, output_file, sample_rate=8000):
    audio = AudioSegment.from_mp3(input_file)
    audio = audio.set_frame_rate(sample_rate)
    audio = audio.set_sample_width(1)
    audio_samples = np.array(audio.get_array_of_samples())
    audio_samples = audio_samples / 2 ** 15
    mulaw_audio = mulaw_encode(audio_samples)

    with open(output_file, 'wb') as f:
        f.write(mulaw_audio.tobytes())

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'Uso: {sys.argv[0]} <archivo_MP3>')
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = os.path.splitext(input_file)[0] + '.ulaw'

    convert_mp3_to_mulaw(input_file, output_file)
    print(f'Archivo convertido y guardado en: {output_file}')

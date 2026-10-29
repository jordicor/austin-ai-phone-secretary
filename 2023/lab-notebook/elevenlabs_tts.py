import requests
import json


def tts11AI(key: str, text: str, voice_id: str = 'TxGEqnHWrfWFTfGW9XjX', stability: float = 0.35, similarity_boost: float = 0.75) -> bytes:
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

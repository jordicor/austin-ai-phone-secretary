import openai
from fastapi import FastAPI, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
from functions import FUNCTIONS

# Configuración de GPT-3.5
openai_key ='<OPENAI_API_KEY>'
API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

app = FastAPI()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=3333, ssl_certfile='static/sec/cert.pem', ssl_keyfile='static/sec/privkey.pem')

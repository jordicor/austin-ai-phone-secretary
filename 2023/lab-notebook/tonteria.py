texto = """import io
import os
import re
import sys
import json
import time
import uuid
import wave
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
from io import BytesIO
from queue import Queue
from asyncio import sleep
from deepgram import Deepgram
from dotenv import load_dotenv
from pydub import AudioSegment
from twilio.rest import Client
from aiohttp import ClientSession
from multiprocessing import Value
from starlette.routing import Route
from queue import PriorityQueue, Queue
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, VoiceResponse, Stream
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import numpy as np
from scipy.io import wavfile
import re
import threading
import time
import emoji
from queue import PriorityQueue, Queue
from urllib.parse import urlencode"""

# Dividimos el texto en líneas
lineas = texto.split("\n")

# Obtenemos la longitud de cada línea y la almacenamos en un diccionario
longitudes = {linea: len(linea) for linea in lineas}

# Ordenamos las líneas según su longitud y, en caso de tener la misma longitud, alfabéticamente
lineas_ordenadas = sorted(lineas, key=lambda x: (longitudes[x], x))

# Unimos las líneas ordenadas en un solo texto
texto_ordenado = "\n".join(lineas_ordenadas)

# Imprimimos el texto ordenado
print(texto_ordenado)

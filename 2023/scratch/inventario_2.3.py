import openai
import os
import json
import asyncio

# Configura tu clave de API de OpenAI
openai.api_key ='<OPENAI_API_KEY>'
API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Inicia el inventario
inventory = {}

# Interactúa con el modelo
# Inicia una nueva conversación
conversation = [
    {"role": "system", "content": "Imagina que eres un personaje de un videojuego. Tendrás diferentes opciones a elegir para resolver unos problemas. Las funciones las tienes que llamar de una en una. No te puedes inventar funciones. Si debes decir algo debes hacerlo por texto. Si debes realizar multiples acciones o se te pide que hagas múltiples acciones, las realizarás una a una con las funciones, si es que existe una para eso. Si una función no existe, la ignoras sin decir nada y haz la siguiente función o acción."},
]

FUNCTIONS = [
    {
        'name': 'acciones-con-objetos',
        'description': "Con esta funcion puedes elegir que acciones puedes realizar con los objetos.",
        'parameters': {
            'type': 'object',
            'properties': {
                'accion': {
                    'type': 'string',
                    'enum': ['soltar', 'usar'],
                    'description': 'La acción que quieres realizar.'
                },
                'objetos': {
                    'type': 'string',
                    'enum': ['Tesla', 'patinete', 'smartphone', 'iPad', 'agenda'],
                    'description': 'Los objetos con los que puedes interactuar'
                }
            },
            'required': ['accion', 'objetos']
        }
    },
    {
        "name": "do_nothing",
        "description": "Function when you have nothing to do (waiting for your boss, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            "required": ["more_actions"],
        },
    },
]

FUNCTIONS_TESLA = {
    'name': 'Tesla',
    'description': "Con esta funcion puedes elegir que acciones puedes realizar con los objetos.",
    'parameters': {
        'type': 'object',
        'properties': {
            'accion': {
                'type': 'string',
                'enum': ['pisar', 'aflojar', 'pisar a fondo', 'levantar pie'],
                'description': 'La acción que quieres realizar.'
            },
            'pedal': {
                'type': 'string',
                'enum': ['frenar', 'acelerar'],
                'description': 'El pedal que quieres utilizar.'
            }
        },
        'required': ['accion', 'pedal']
    }
}

FUNCTIONS_SMARTPHONE = {
    'name': 'smartphone',
    'description': "Con esta funcion puedes elegir que acciones puedes realizar con el teléfono.",
    'parameters': {
        'type': 'object',
        'properties': {
            'accion': {
                'type': 'string',
                'enum': ['llamar', 'colgar', 'marcar'],
                'description': 'La acción que quieres realizar.'
            },
            'numero': {
                'type': 'string',
                'description': 'El número que quieres marcar.'
            }
        },
        'required': ['accion', 'numero']
    }
}

async def manage_inventory(action, object_name):
    if action == 'usar':
        if object_name == 'Tesla':
            FUNCTIONS.append(FUNCTIONS_TESLA)
        elif object_name == 'smartphone':
            FUNCTIONS.append(FUNCTIONS_SMARTPHONE)
    elif action == 'soltar':
        FUNCTIONS[:] = [d for d in FUNCTIONS if d.get('name') != object_name]
        
        
async def llamar_gpt(conversation):
    #print(f"conversacion al llamar a GPT: {conversation}")
    # funcion llamada GPT
    response = openai.ChatCompletion.create(
        #model="gpt-3.5-turbo",
        model="gpt-4-0613",
        temperature=0.1,
        messages=conversation,
        functions=FUNCTIONS
    )
    return response
    
async def gestionar_gpt(response):
# funcion gestiona gestiona(response)
    response_root = response["choices"][0]["message"]

    # Step 2: check if GPT wanted to call a function
    if response_root.get("function_call"):
        await gestionar_funcion(response)
        #llamar a funcion de GPT response_function = llama_gpt(conversation)
        #print("pues voy a llamar a llamar_gpt")
        response_function = await llamar_gpt(conversation)
        #print("justo antes de gestionar_gpt dentro de gestionar_gpt")
        await gestionar_gpt(response_function)
            
        #print("estoy fuera del more actions y despues del gestionar_gpt en gestionar_gpt! yay")
    else:
        await gestionar_txt(response)


async def gestionar_funcion(response):
        response_function = response['choices'][0]['message'].get('function_call') # obtén el texto de la respuesta
        
        conversation.append({"role": "function","name":"interaccion", "content": f'{{{response_function}}}'})
        
        function_name = response_function.get("name")
        function_args = json.loads(response_function.get("arguments"))
        
        print("---")
        print(f"funcion: {function_name}")
        print(f"argumentos: {function_args}")
        print("---")

        
        if function_args:
            more_functions = function_args.get("more_functions")
            item = function_args.get("item")
            accion_args = function_args.get("accion")
        
            if function_name == "acciones-con-objetos":
                    object_name = function_args.get("objetos")
                    await manage_inventory(accion_args,object_name)
                    #print("antes de gpt_message en gestionar_funcion")
                    gpt_message = {
                        "role": "function",
                        "name": "interaccion",
                        "content": f'{{"success": "True", "accion": "{accion_args}"}}'
                    }
            elif function_name == "do_nothing":
                gpt_message = {
                    "role": "function",
                    "name": "do_nothing",
                    "content": f'{{"success": "True"}}'
                }
            else:
                gpt_message = {
                    "role": "function",
                    "name": f"{function_name}",
                    #"content": f'{{"success": "False", "reason": "Function not Found"}}'
                    "content": f'{{"success": "True"}}'
                }
           
            
            # Añade la respuesta del modelo a la conversación para que pueda ver su propia respuesta cuando genera la próxima
            #print(f"este es el resultado de lo que ha pedido {gpt_message}")
            
            conversation.append(gpt_message)
        

            

async def gestionar_txt(response):

    response_message = response['choices'][0]['message'].get('content') # obtén el texto de la respuesta

    if response_message == None:
        print("no ha respondido texto")
        print(response['choices'][0]['message'])
    else:
        actions = response_message.split(', ')  # divide el texto en acciones

        print("ChatGPT: ", response_message)

        # Añade la respuesta del modelo a la conversación para que pueda ver su propia respuesta cuando genera la próxima
        conversation.append({"role": "assistant", "content": response_message})


######## ESTE ES EL MAIN

async def Main():
    while True:
        message = input("Tú: ")
        conversation.append({"role": "user", "content": message})
        
        # aqui se llama a GPT
        response = await llamar_gpt(conversation)
        tutia = await gestionar_gpt(response)


asyncio.run(Main())

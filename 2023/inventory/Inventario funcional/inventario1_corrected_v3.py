import asyncio
import openai
import os
import json

# Configura tu clave de API de OpenAI
openai.api_key ='<OPENAI_API_KEY>'
API_ENDPOINT = "https://api.openai.com/v1/chat/completions"

# Inicia el inventario
inventory = {}
hand = None

# Define una función para manejar el inventario y la mano
def handle_objects(action, item):
    global hand
    success = True
    if action == 'encontrar':
        if item in inventory:
            inventory[item] += 1
        else:
            inventory[item] = 1
        print(f"Has encontrado el objeto: {item} y lo has guardado en el inventario")
    elif action == 'coger':
        if hand is not None:
            print(f"Ya tienes el objeto: {hand} en la mano. Debes usar o guardar antes de coger otro objeto.")
            success = False
        else:
            if item in inventory and inventory[item] > 0:
                inventory[item] -= 1
                hand = item
                print(f"Has cogido el objeto: {item} del inventario")
            else:
                print(f"No tienes el objeto: {item} en tu inventario para coger")
                success = False
    elif action == 'usar':
        if hand == item:
            print(f"Has usado el objeto: {item}")
        else:
            print(f"No tienes el objeto: {item} en la mano para usar")
            success = False
    elif action == 'guardar':
        if hand == item:
            inventory[item] += 1
            hand = None
            print(f"Has guardado el objeto: {item} en el inventario")
        else:
            print(f"No tienes el objeto: {item} en la mano para guardar")
            success = False
    return inventory, hand, success

# Interactúa con el modelo
# Inicia una nueva conversación
conversation = [
    {"role": "system", "content": "Imagina que eres un personaje de un videojuego. Tendrás diferentes opciones a elegir para resolver unos problemas. Busca cual es el objeto necesario para resolver tu problema. Solo puedes coger un objeto cuando los encuentres. Puedes realizar varias acciones a la vez con el mismo objeto o si debes soltar un objeto si pueden ser objetos diferentes. Por favor, responde con una serie de comandos separados por comas, cada uno de los cuales contiene una acción y un objeto. Por ejemplo, 'Encontrar manzana, Coger manzana, Usar manzana, Guardar manzana'. Recuerda que solo puedes coger el item del inventario si no tienes nada en la mano, solo puedes usar el item si lo tienes en la mano, y solo puedes guardar el item en el inventario si lo tienes en la mano."},
]


FUNCTIONS = [
    {
        'name': 'movimientos',
        'description': "Con esta funcion puedes elegir que movimientos fisicos puedes realizar.",
        'parameters': {
            'type': 'object',
            'properties': {
                'accion': {
                    'type': 'string',
                    'enum': ['correr', 'caminar', 'saltar', 'agachar', 'trepar', 'reptar'],
                    'description': 'La acción que quieres realizar.'
                },
                'more_actions': {
                    'type': 'boolean',
                    'description': 'Indicates whether more actions will be performed after this one'
                }
            },
            'required': ['accion', 'more_actions']
        }
    },
    {
        'name': 'interaccion',
        'description': "Con esta funcion puedes interactuar con objetos que se te hayan indicado que tienes a tu alcance.",
        'parameters': {
            'type': 'object',
            'properties': {
                'accion': {
                    'type': 'string',
                    'enum': ['coger', 'soltar', 'lanzar', 'guardar', 'usar', 'entregar'],
                    'description': 'La interaccion que quieres realizar con un objeto.'
                },
                'item': {
                    'type': 'string',
                    #'inventario': inventario,
                    'description': 'El objeto con el que quieres interactuar.'
                },

                'more_actions': {
                    'type': 'boolean',
                    'description': 'Indicates whether more actions will be performed after this one'
                }
            },
            'required': ['accion', 'item', 'more_actions']
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

async def llamar_gpt(conversation):
    # funcion llamada GPT
    response = openai.ChatCompletion.create(
        #model="gpt-3.5-turbo",
        model="gpt-4-0613",
        messages=conversation,
        functions=FUNCTIONS
    )
    return response
    
    
    
async def gestionar_gpt(response):
# funcion gestiona gestiona(response)
    response_root = response["choices"][0]["message"]

    # Step 2: check if GPT wanted to call a function
    if response_root.get("function_call"):
        more_actions = await gestionar_funcion(response)
        #llamar a funcion de GPT response_function = llama_gpt(conversation)
        print("pues voy a llamar a llamar_gpt")
        response_function = await llamar_gpt(conversation)
        print("just antes de gestionar_gpt dentro de gestionar_gpt")
        await gestionar_gpt(response_function)

        while more_actions:
            print("toy dentro del more actions! uee")
            more_actions = await gestionar_funcion(response)
            #funcion gestiona(response_function)
            
            #llamar a funcion de GPT response_function = llama_gpt(conversation)
            response_function = await llamar_gpt(conversation)
        print("estoy fuera del more actions! yay")
    else:
        await gestionar_txt(response)


async def gestionar_funcion(response):
        response_function = response['choices'][0]['message'].get('function_call') # obtén el texto de la respuesta
        function_name = response_function.get("name")
        function_args = json.loads(response_function.get("arguments"))
        if function_args:
            more_actions = function_args.get("more_actions")
            item = function_args.get("item")
        else:
            pass
        
        if function_name == "movimientos":
            print(f"argumentos: {function_args}")
            gpt_message = {
                "role": "function",
                "name": function_name,
                "content": {
                    "success": "True"
                }
            }
            # Añade la respuesta del modelo a la conversación para que pueda ver su propia respuesta cuando genera la próxima
            conversation.append(gpt_message)
        
        return more_actions

            

async def gestionar_txt(response):

    response_message = response['choices'][0]['message'].get('content') # obtén el texto de la respuesta

    if response_message == None:
        print("no ha respondido texto")
        print(response['choices'][0]['message'])
    else:
        actions = response_message.split(', ')  # divide el texto en acciones

        # Supón que cada acción es una frase que contiene una acción y un objeto
        for action in actions:
            words = action.split()  # divide la frase en palabras
            if len(words) >= 2:  # solo procesa la frase si contiene al menos una acción y un objeto
                action = words[0].lower()
                item = ' '.join(words[1:]).rstrip('.')  # toma todo después de la primera palabra como el objeto y elimina los puntos del final
                inventory, hand, success = handle_objects(action, item)
                if not success:
                    break

        print("ChatGPT: ", response_message)
        print("Inventario: ", inventory)
        print("En la mano: ", hand)

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

import openai
import os
import json
import asyncio

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
    {"role": "system", "content": "Imagina que eres un personaje de un videojuego. Tendrás diferentes opciones a elegir para resolver unos problemas. Las funciones las tienes que llamar de una en una. No te puedes inventar funciones. Si debes decir algo debes hacerlo por texto. Si debes realizar multiples acciones o se te pide que hagas múltiples acciones, las realizarás una a una con las funciones, si es que existe una para eso. Si una función no existe, la ignoras sin decir nada y haz la siguiente función o acción. En la funcion interaccion puedes usar cosas, por ejemplo si te encuentras con un coche puedes mirar si tienes su funcion para usarla y sus acciones "},
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
                'more_functions': {
                    'type': 'boolean',
                    'description': 'Indicates whether more functions will be called after this one'
                }
            },
            'required': ['accion', 'more_functions']
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
                'inventario': {
                    'type': "array",
                    'description': "The objects that you can use",
                    'items': {
                        'coche': {
                            'type': "string",
                            'object_name': 'coche',
                            'object_description': "A car to move around.",
                        },
                        'moto': {
                            'type': "string",
                            'object_name': 'moto',
                            'object_description': "A moto to move around narrow streets.",
                        }
                    }
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
async def manage_inventory(action, object_name):
    if action == 'usar':
        print("ha entrado en usar")
        # Si la acción es 'pickup', añadimos un nuevo campo con las propiedades del objeto
        FUNCTIONS[0]['parameters']['properties'][object_name] = {
            'type': "array",
            'description': "The actions you can apply",
            'items': {
                'accelerate': {
                    'type': "string",
                    'object_name': 'accelerate',
                    'object_description': "Use this function to accelerate the vehicle to move forward",
                },
                'stop': {
                    'type': "string",
                    'object_name': 'stop',
                    'object_description': "Use this function to stop your vehicle",
                }
            }
        }
    elif action == 'soltar':
        print("ha entradp en soltar")
        # Si la acción es 'drop', eliminamos el campo correspondiente al objeto
        del tstFUNCTIONS[0]['parameters']['properties'][object_name]
        
async def llamar_gpt(conversation):
    print(f"conversacion al llamar a GPT: {conversation}")
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
        more_functions = await gestionar_funcion(response)
        #llamar a funcion de GPT response_function = llama_gpt(conversation)
        print("pues voy a llamar a llamar_gpt")
        response_function = await llamar_gpt(conversation)
        print("justo antes de gestionar_gpt dentro de gestionar_gpt")
        await gestionar_gpt(response_function)
            
        print("estoy fuera del more actions y despues del gestionar_gpt en gestionar_gpt! yay")
    else:
        await gestionar_txt(response)


async def gestionar_funcion(response):
        response_function = response['choices'][0]['message'].get('function_call') # obtén el texto de la respuesta
        
        conversation.append({"role": "function","name":"interaccion", "content": f'{{{response_function}}}'})
        
        print(f"response_function: {response_function}")
        
        function_name = response_function.get("name")
        function_args = json.loads(response_function.get("arguments"))
        
        print(f"argumentos: {function_args}")

        
        if function_args:
            more_functions = function_args.get("more_functions")
            item = function_args.get("item")
            accion_args = function_args.get("accion")
        else:
            pass
        
        
        
        
        
        
        if function_name == "movimientos":
            gpt_message = {
                "role": "function",
                "name": "movimientos",
                "content": f'{{"success": "True", "accion": "{accion_args}"}}'
            }
        elif function_name == "interaccion":
                object_name = function_args.get("inventario")[0]  # get the first element from the list
                await manage_inventory(accion_args,object_name)
                print("antes de gpt_message en gestionar_funcion")
                gpt_message = {
                    "role": "function",
                    "name": "interaccion",
                    "content": f'{{"success": "True", "accion": "{accion_args}"}}'
                }
        # Añade la respuesta del modelo a la conversación para que pueda ver su propia respuesta cuando genera la próxima
        
        print(f"esta es el resultado de lo que ha pedido {gpt_message}")
        
        conversation.append(gpt_message)
        
        return more_functions

            

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
        #print("Inventario: ", inventory)
        #print("En la mano: ", hand)

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

import functions
from inventory import Inventory
from chatbot import ChatGPT

# Crear un inventario
inventory = Inventory()

# Añadir los objetos al inventario
for object_name, object_info in functions.FUNCTIONS[0]['parameters']['properties']['object']['items'].items():
    inventory.pick_up(object_info['object_name'], object_info['object_description'], [])

# Crear el bot
bot = ChatGPT(inventory)

# Interactuar con el bot
while True:
    user_input = input(">>> ")
    if user_input == 'quit':
        break
    response = bot.respond(user_input)
    print(response)



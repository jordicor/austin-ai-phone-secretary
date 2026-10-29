class ChatGPT:
    def __init__(self, inventory):
        self.inventory = inventory

    def respond(self, user_input):
        action, item = user_input.split(' ', 1)
        
        if action == 'pickup':
            if item in self.inventory.list_objects():
                return f"Ya tengo un(a) {item} en mi inventario."
            else:
                self.inventory.pick_up(item, 'descripción', [])  # Aquí deberías buscar la descripción y acciones reales del objeto en tu data
                return f"He recogido el(la) {item}."
        
        elif action == 'drop':
            if item not in self.inventory.list_objects():
                return f"No tengo un(a) {item} en mi inventario."
            else:
                self.inventory.drop(item)
                return f"He soltado el(la) {item}."
        
        elif action == 'use':
            if item not in self.inventory.list_objects():
                return f"No puedo usar el(la) {item} porque no está en mi inventario. Intenta recogerlo primero."
            else:
                return f"Estoy usando el(la) {item}."



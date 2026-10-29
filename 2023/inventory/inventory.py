class InventoryObject:
    def __init__(self, name, description, actions):
        self.name = name
        self.description = description
        self.actions = actions

class Inventory:
    def __init__(self):
        self.objects = {}

    def pick_up(self, object_name, object_description, actions):
        self.objects[object_name] = InventoryObject(object_name, object_description, actions)

    def drop(self, object_name):
        if object_name in self.objects:
            del self.objects[object_name]

    def list_objects(self):
        return [obj.name for obj in self.objects.values()]

    def get_object(self, object_name):
        return self.objects.get(object_name, None)

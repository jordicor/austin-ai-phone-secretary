FUNCTIONS = [
    {
        'name': "inventory",
        'description': "This function manages the inventory of the assistant. If you don't have equipped the object that you want to use you have to pick it up and you'll receive the list of functions of that object to know how to use it. ",
        'parameters': {
            'type': "object",
            'properties': {
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'},
                'action': {
                    'type': 'string',
                    'enum': ['pickup', 'drop'],
                    'description': 'The action to perform with the object that you want to use.'
                },
                'object': {
                    'type': "array",
                    'description': "The objects that you can pickup",
                    'items': {
                        'phone': {
                            'type': "string",
                            'object_name': 'Cisco Phone',
                            'object_description': "A Cisco IP Phone allows you to make, receive and transfer calls.",
                        },
                        'email': {
                            'type': "string",
                            'object_name': 'Email',
                            'object_description': "Allows you to access email and sent it.",
                        },
                        'fax': {
                            'type': "string",
                            'object_name': 'Fax',
                            'object_description': "Allows you to access fax and send it.",
                        },
                        'sandwich': {
                            'type': "string",
                            'object_name': 'Sandwich',
                            'object_description': "Allows you to eat if u are hungry.",
                        },
                    }
                }
            },
            'required': ["action", "object_name", "more_actions"]
        },
    },
]

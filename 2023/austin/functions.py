tstFUNCTIONS = [
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
                            'object_description': "Allows you to access email and your boss email.",
                        }
                    }
                }
            },
            'required': ["action", "object_name", "more_actions"]
        },
    }                
]


FUNCTIONS = [
    {
        'name': 'actions-with-objects',
        'description': "With this function you can choose what actions you can perform with the objects",
        'parameters': {
            'type': 'object',
            'properties': {
                'more_actions': {'type': 'string', 'description': 'You have to return always True.'},
                'action': {
                    'type': 'string',
                    'enum': ['drop', 'use'],
                    'description': 'The action you want to do'
                },
                'objects': {
                    'type': 'string',
                    'enum': ['Tesla', 'skateboard', 'Cisco-Phone', 'iPad', 'agenda'],
                    'description': 'The objects you can interact with.'
                }
            },
            'required': ['action', 'objects', 'more_actions']
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


CISCOPHONE = [
    {
        'name': 'put_on_hold',
        'description': "This Cisco-Phone function puts the current call on hold, and changes the scenario to 'call on hold'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string','description': 'The Call SID, representing the active line number'},
                'message': {'type': 'string','description': 'The message to say to the caller before activating the hold button'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'message', 'more_actions']
        }
    },
    {
        'name': 'transfer_call',
        'description': "This Cisco-Phone function performs a regular transfer or an a   ttended transfer, allowing a conversation with the transfer recipient before the transfer is completed. The function changes the scenario to 'call transferred'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string', 'description': 'The Call SID, representing the active line number'},
                'type': {'type': 'string', 'enum': ['cold', 'warm'], 'description': 'Cold or warm transfer'},
                'number': {'type': 'string', 'description': 'The number or call_sid line number to transfer the call to'},
                'call_message': {'type': 'string', 'description': 'The message to speak to the transfer recipient'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one, return True the first time you use it'}
            },
            'required': ['call_sid', 'number', 'call_message', 'more_actions']
        }
    },
    {
        'name': 'cancel_transfer',
        'description': "This Cisco-Phone function cancels a call that is in process to be transfered but has been rejected by the recipient. It will hangup with the recipient and retrieve the call with the person waiting to be transfered. The function changes the scenario to 'transfer canceled'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string', 'description': 'The Call SID, representing the active line number'},
                'previous_number': {'type': 'string', 'description': 'The call_sid of the previous active_line'},
                'hangup_message': {'type': 'string', 'description': 'This is the message to be communicated to the recipient who has rejected the call transfer, before the call is hung up. This message should acknowledge the recipient\'s decision to reject the transfer, such as "OK, I will cancel the call transfer. Thank you.". After this message is delivered and the call is hung up, the function will retrieve the call with the person who was initially waiting to be transferred.'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'previous_number', 'hangup_message', 'more_actions']
        }
    },
    
    {
        'name': 'switch_call',
        'description': "This Cisco-Phone function switches between the current active call and a call on hold. The function changes the scenario to 'switched call'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid_active': {'type': 'string', 'description': 'The Call SID of the active call, representing the active line number'},
                'call_sid_hold': {'type': 'string', 'description': 'The Call SID of the call on hold'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid_active', 'call_sid_hold', 'more_actions']
        }
    },
    {
        'name': 'retrieve_call',
        'description': "This Cisco-Phone function retrieves a call that was put on hold. After this function is called, the scenario changes to 'call retrieved', and the active line becomes the one specified by 'retrieve_sid'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string', 'description': 'The Call SID, representing the active line number'},
                'retrieve_sid': {'type': 'string', 'description': 'The Call SID of the call that you want to retrieve.'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'retrieve_sid', 'more_actions']
        }
    },
    {
        'name': 'hang_up_call',
        'description': "This Cisco-Phone function hangs up the call with the Call SID specified. After this function is called, the scenario changes to 'call hung up'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string', 'description': 'The Call SID, representing the active line number'},
                'hangup_sid': {'type': 'string', 'description': 'The Call SID of the call that you want to hang up.'},
                'hangup_message': {"type": "string","description": "This is the message to be communicated to the caller before the call is ended. This message should acknowledge that the call is about to be hung up."},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'hangup_sid', 'more_actions']
        }
    },
    {
        "name": "answer_call",
        "description": "Function Cisco-Phone to answer a call when phone is ringing. After this function is called, the scenario changes to 'on the phone'.",
        "parameters": {
            "type": "object",
            "properties": {
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            "required": ["more_actions"],
        },
    },
]















FUNCTIONS_PHONE = [
    {
        'name': 'put_on_hold',
        'description': "This function puts the current call on hold, and changes the scenario to 'call on hold'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string','description': 'The Call SID, representing the active line number'},
                'message': {'type': 'string','description': 'The message to say to the caller before activating the hold button'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'message', 'more_actions']
        }
    },
    {
        'name': 'transfer_call',
        'description': "This function performs a regular transfer or an a   ttended transfer, allowing a conversation with the transfer recipient before the transfer is completed. The function changes the scenario to 'call transferred'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string', 'description': 'The Call SID, representing the active line number'},
                'type': {'type': 'string', 'enum': ['cold', 'warm'], 'description': 'Cold or warm transfer'},
                'number': {'type': 'string', 'description': 'The number or call_sid line number to transfer the call to'},
                'call_message': {'type': 'string', 'description': 'The message to speak to the transfer recipient'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'number', 'call_message', 'more_actions']
        }
    },
    {
        'name': 'cancel_transfer',
        'description': "This function cancels a call that is in process to be transfered but has been rejected by the recipient. It will hangup with the recipient and retrieve the call with the person waiting to be transfered. The function changes the scenario to 'transfer canceled'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string', 'description': 'The Call SID, representing the active line number'},
                'previous_number': {'type': 'string', 'description': 'The call_sid of the previous active_line'},
                'hangup_message': {'type': 'string', 'description': 'This is the message to be communicated to the recipient who has rejected the call transfer, before the call is hung up. This message should acknowledge the recipient\'s decision to reject the transfer, such as "OK, I will cancel the call transfer. Thank you.". After this message is delivered and the call is hung up, the function will retrieve the call with the person who was initially waiting to be transferred.'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'previous_number', 'hangup_message', 'more_actions']
        }
    },
    
    {
        'name': 'switch_call',
        'description': "This function switches between the current active call and a call on hold. The function changes the scenario to 'switched call'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid_active': {'type': 'string', 'description': 'The Call SID of the active call, representing the active line number'},
                'call_sid_hold': {'type': 'string', 'description': 'The Call SID of the call on hold'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid_active', 'call_sid_hold', 'more_actions']
        }
    },
    {
        'name': 'retrieve_call',
        'description': "This function retrieves a call that was put on hold. After this function is called, the scenario changes to 'call retrieved', and the active line becomes the one specified by 'retrieve_sid'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string', 'description': 'The Call SID, representing the active line number'},
                'retrieve_sid': {'type': 'string', 'description': 'The Call SID of the call that you want to retrieve.'},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'retrieve_sid', 'more_actions']
        }
    },
    {
        'name': 'hang_up_call',
        'description': "This function hangs up the call with the Call SID specified. After this function is called, the scenario changes to 'call hung up'.",
        'parameters': {
            'type': 'object',
            'properties': {
                'call_sid': {'type': 'string', 'description': 'The Call SID, representing the active line number'},
                'hangup_sid': {'type': 'string', 'description': 'The Call SID of the call that you want to hang up.'},
                'hangup_message': {"type": "string","description": "This is the message to be communicated to the caller before the call is ended. This message should acknowledge that the call is about to be hung up."},
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            'required': ['call_sid', 'hangup_sid', 'more_actions']
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
    {
        "name": "answer_call",
        "description": "Function to answer a call when phone is ringing. After this function is called, the scenario changes to 'on the phone'.",
        "parameters": {
            "type": "object",
            "properties": {
                'more_actions': {'type': 'boolean', 'description': 'Indicates whether more actions will be performed after this one'}
            },
            "required": ["more_actions"],
        },
    },
]

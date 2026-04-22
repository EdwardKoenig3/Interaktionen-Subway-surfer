def map_command(command):
    mapping = {
        "links": "left",
        "rechts": "right",
        "oben": "jump",
        "unten": "slide"
    }
    
    return mapping.get(command.lower(), "unknown command")


# Test
commands = ["links", "rechts", "oben", "unten", "start"]
    
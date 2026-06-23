
def map_command(text):
    # Wichtig: Wir nutzen 'in', um zu schauen, ob das Wort in der Liste vorkommt
    
    if text in ["links", "linkss","left"]:
        return [("/game/voice/left", 1)]
    
   
    elif text in ["middle","center"]: # Hier geht ==, da es nur ein Wort ist
        return [("/game/voice/center", 1)]

    elif text in ["rechts", "rechtss","right"]: # Geändert von == zu in
        return [("/game/voice/right", 1)]

    elif text in ["hoch", "jump", "jumpp","oben","up"]: # Geändert von == zu in
        return [("/game/voice/jump", 1)]

    elif text in ["runter", "slide","unten","duck", "ducken", "cover", "sneek"]: # Geändert von == zu in
        return [("/game/voice/slide", 1)]

    return []
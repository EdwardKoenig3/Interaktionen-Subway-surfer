def map_command(text):
    # Wichtig: Wir nutzen 'in', um zu schauen, ob das Wort in der Liste vorkommt
    
    if text in ["links", "linkss","left"]:
        return [("/game/left", 1)]
    
    elif text == "mitte": # Hier geht ==, da es nur ein Wort ist
        return [("/game/center", 1)]

    elif text in ["rechts", "rechtss","right"]: # Geändert von == zu in
        return [("/game/right", 1)]

    elif text in ["hoch", "jump", "jumpp","oben","up"]: # Geändert von == zu in
        return [("/game/jump", 1)]

    elif text in ["runter", "slide","unten","duck", "ducken"]: # Geändert von == zu in
        return [("/game/slide", 1)]

    return []
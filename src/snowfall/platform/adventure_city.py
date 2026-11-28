"""Server-owned city atlas. Reuses existing artwork until the artwork pass."""
CITY = "city"
CASE_SCENES = frozenset({"office", "alley"})
# Opening day, column, row, access flag, hidden until discovered.
LOCATIONS = {
    "office": (1, 1, 1, None, False),
    "hotel": (1, 2, 1, None, False),
    "station": (2, 3, 1, None, False),
    "post_office": (4, 4, 1, None, False),
    "market": (1, 1, 2, None, False),
    "alley": (1, 2, 2, "door_open", False),
    "ice_house": (3, 3, 2, None, False),
    "press_room": (5, 4, 2, None, False),
    "archive": (1, 1, 3, "archive_found", True),
    "telegraph": (6, 3, 3, None, False),
    "square": (7, 4, 3, None, False),
}
DISCOVERIES = {
    "market_token": ("Winter market token", "A brass souvenir from the old market."),
    "hotel_card": ("Grand Hotel calling card", "A keepsake from the lobby concierge."),
    "station_ticket": ("Midnight platform ticket", "An unpunched winter ticket."),
    "ice_stamp": ("Ice-house stamp", "A frosted blue warehouse seal."),
    "post_mark": ("Christmas postmark", "A special winter stamp."),
    "press_print": ("Snowfall Wire proof", "An early printing of the winter edition."),
    "telegraph_ribbon": ("Telegraph ribbon", "A short piece of retired message tape."),
    "square_star": ("Winter square star", "A little brass star from the final celebration."),
    "archive_badge": ("Hidden archive badge", "A keepsake from a forgotten room."),
}


def _spot(label, x, y, text, **effects):
    return {"label": label, "x": x, "y": y, "text": text, **effects}


def _scene(title, description, art, targets):
    return {"title": title, "description": description,
            "art": "/art/v290/mysteries/" + art, "targets": targets, "uses": {}}


CITY_SCENES = {
    CITY: {"title": "The Winter Underworld",
           "description": "Walk the snowy streets. New buildings open daily. Some entrances must be discovered.",
           "art": "/static/snowfall-city-wallpaper.webp", "targets": {}, "uses": {}},
    "market": _scene("Winter Market", "Lanterns glow over the stalls.", "day_4.webp", {
        "stall": _spot("Trader's display", 24, 48, "A brass market token is offered as a keepsake.",
                      collect=["market_token"], flag="market_token"),
        "notice": _spot("Market notice", 72, 32, "The Grand Hotel keeps old city records below its lobby."),
    }),
    "hotel": _scene("Grand Hotel", "An old concierge watches the snow.", "day_1.webp", {
        "concierge": _spot("Concierge", 36, 48, "The concierge welcomes you.", dialogue="concierge"),
        "directory": _spot("Old directory", 75, 28, "The directory mentions a disused service entrance.",
                          flag="hotel_directory"),
        "hatch": _spot("Disused service entrance", 72, 76,
                      "The concierge lifts the latch. A forgotten archive is now marked on your map.",
                      requires=["market_token", "hotel_directory", "concierge_permission"], flag="archive_found"),
    }),
    "station": _scene("Midnight Railway Station", "Search the public waiting room.", "day_2.webp", {
        "ticket": _spot("Ticket tray", 28, 65, "An unused winter ticket is yours to keep.", collect=["station_ticket"]),
        "board": _spot("Departure board", 73, 28, "Late trains are running despite the snow."),
    }),
    "ice_house": _scene("Ice House", "The public reception has reopened.", "day_3.webp", {
        "desk": _spot("Reception desk", 30, 60, "A clerk offers an old warehouse stamp.", collect=["ice_stamp"]),
        "frost": _spot("Frosted wall", 76, 35, "Ice crystals sparkle in the lantern light."),
    }),
    "post_office": _scene("Christmas Post Office", "The sorting room is busy.", "day_4.webp", {
        "stamp": _spot("Stamp counter", 30, 63, "The postmaster has a commemorative postmark.", collect=["post_mark"]),
        "sacks": _spot("Mail sacks", 75, 49, "Every sack is labelled for a different district."),
    }),
    "press_room": _scene("Snowfall Wire Press Room", "The presses are warming up.", "day_5.webp", {
        "proof": _spot("Printer's proof", 25, 62, "A spare winter edition proof is yours.", collect=["press_print"]),
        "press": _spot("Printing press", 74, 39, "The machinery rattles to life."),
    }),
    "telegraph": _scene("Telegraph Office", "The wires hum quietly.", "day_6.webp", {
        "tape": _spot("Discarded tape", 30, 60, "A retired ribbon makes a curious souvenir.", collect=["telegraph_ribbon"]),
        "wire": _spot("Wire cabinet", 74, 36, "The lines connect distant streets."),
    }),
    "square": _scene("Christmas Square", "The city gathers beneath the Christmas tree.", "day_7.webp", {
        "tree": _spot("Tree decorations", 48, 30, "A spare brass star rests beside the tree.", collect=["square_star"]),
        "bench": _spot("Snowy bench", 77, 74, "The whole city seems peaceful."),
    }),
    "archive": _scene("Hidden Hotel Archive", "Dusty records line the shelves.", "classified_dossier.webp", {
        "cabinet": _spot("Forgotten cabinet", 25, 58, "A forgotten archive badge glints in the dust.", collect=["archive_badge"]),
        "register": _spot("Old visitor register", 72, 35, "Its pages preserve decades of winter visitors."),
    }),
}
CITY_DIALOGUES = {
    "concierge": {
        "speaker": "Grand Hotel concierge", "text": "Welcome, detective. What brings you here?",
        "choices": {
            "card": {"label": "Ask for a calling card", "text": "Of course. A memento of your visit.", "collect": ["hotel_card"]},
            "archive": {"label": "Ask about the old service entrance",
                        "requires": ["market_token", "hotel_directory"], "flag": "concierge_permission",
                        "text": "Ah, a market token. You may explore the old service entrance."},
            "leave": {"label": "End conversation", "close": True, "text": "The concierge returns to the desk."},
        },
    },
}


def available(key, state, day):
    if key == CITY:
        return True
    loc = LOCATIONS.get(key)
    return bool(loc and day is not None and day >= loc[0]
                and (not loc[3] or loc[3] in state["flags"]))


def normalize_location(state, day):
    # QA can rewind the day; future buildings must not remain accessible.
    if not available(state["scene"], state, day):
        state["scene"] = CITY
        state["dialogue"] = None
        state["message"] = "This location is not open today. Return to the city map."


def atlas(state, day, scenes):
    locations = []
    for key, (opens, col, row, flag, hidden) in LOCATIONS.items():
        if hidden and flag not in state["flags"]:
            continue
        is_open = available(key, state, day)
        locations.append({
            "key": key, "title": scenes[key]["title"], "column": col, "row": row,
            "status": "open" if is_open else "locked", "opens_day": opens,
            "visited": key in state["visited"],
            "reason": None if is_open else (
                f"Opens on day {opens}" if day is None or day < opens else "Find a way inside"),
        })
    return {"locations": locations, "visited": sum(x["visited"] for x in locations),
            "visible": len(locations),
            "discoveries": [{"label": DISCOVERIES[k][0], "description": DISCOVERIES[k][1]}
                            for k in state["discoveries"]]}

"""Reusable, server-owned point-and-click adventures. No official rewards.

Content rules are private. Clients receive visible targets and discovered facts,
never prerequisites, solution flags or undiscovered evidence. The same persisted
state supports mouse, touch and keyboard, and is independent of arcade attempts.
"""
from __future__ import annotations

import json
import secrets

from snowfall.services.winter_fun import WinterFunEngine

TABLE = "web_adventure_progress"
CHAPTER = "winter_dispatch"
ITEMS = {
    "brass_key": ("Brass key", "A small key with a snowflake engraved on its bow."),
    "dispatch": ("Dispatch envelope", "A recovered envelope, safely delivered."),
}
EVIDENCE = {
    "tracks": ("Square-heeled footprints", "Fresh square-heeled prints lead toward the loading bay."),
    "receipt": ("Delivery receipt", "The midnight delivery was redirected to the loading bay, not the front door."),
    "stamp": ("Blue wax seal", "The recovered envelope bears the same blue wax described by the courier."),
}
# Each target supplies coordinates and an action rule. Requirements and effects
# are evaluated exclusively on the server; adding a scene needs no new API.
SCENES = {
    "office": {
        "title": "The detective's office",
        "description": "A winter dispatch has disappeared. Search the office and speak to the courier.",
        "art": "/static/adventure-office.svg",
        "targets": {
            "drawer": {"label": "Desk drawer", "x": 43, "y": 75,
                       "text": "A little brass key lies under the papers.",
                       "give": ["brass_key"]},
            "window": {"label": "Frosted window", "x": 19, "y": 33,
                       "text": EVIDENCE["tracks"][1], "evidence": ["tracks"]},
            "courier": {"label": "Courier", "x": 65, "y": 49,
                        "text": "The courier looks worried. Ask about the delivery.",
                        "dialogue": "courier"},
            "clock": {"label": "Wall clock", "x": 42, "y": 24,
                      "text": "The clock is running. Nothing unusual here."},
            "door": {"label": "Loading-bay door", "x": 86, "y": 52,
                     "text": "The loading bay is locked. Perhaps something in your satchel fits.",
                     "flag": "door_seen",
                     "when": {"door_open": {"move": "alley", "text": "You step into the snow."}}},
        },
        "uses": {
            "brass_key": {"label": "Use key on loading-bay door", "requires": ["door_seen"],
                          "flag": "door_open", "text": "The brass key turns. The loading bay is open."},
        },
    },
    "alley": {
        "title": "The snowy loading bay",
        "description": "A lantern burns above some abandoned parcels. Search carefully.",
        "art": "/static/adventure-alley.svg",
        "targets": {
            "crates": {"label": "Stack of crates", "x": 25, "y": 69,
                       "text": "Only empty packing straw. Someone has already searched here."},
            "parcel": {"label": "Snow-covered parcel", "x": 58, "y": 77,
                       "text": EVIDENCE["stamp"][1], "evidence": ["stamp"],
                       "give": ["dispatch"]},
            "lantern": {"label": "Lantern", "x": 50, "y": 23,
                        "text": "The lantern is warm. The parcel was left here recently."},
            "return": {"label": "Office entrance", "x": 84, "y": 51,
                       "move": "office", "text": "You return to the detective's office."},
        },
        "uses": {},
    },
}
DIALOGUES = {
    "courier": {
        "speaker": "Midnight courier",
        "text": "I was told to leave the dispatch in the usual place. Then a note changed the delivery.",
        "choices": {
            "weather": {"label": "Ask about the weather", "text": "A terrible night for deliveries. The snow is getting deeper."},
            "receipt": {"label": "Ask to see the delivery receipt",
                        "text": EVIDENCE["receipt"][1], "evidence": ["receipt"]},
            "seal": {"label": "Describe the envelope", "text": "A cream envelope with a blue wax seal. Please find it."},
            "report": {"label": "Present your findings", "requires": ["e:tracks", "e:receipt", "e:stamp", "i:dispatch"],
                       "complete": True, "text": "The tracks and receipt led you to the redirected dispatch. The wax seal confirms it. Thank you, detective!"},
            "leave": {"label": "End conversation", "close": True, "text": "The courier waits by the desk."},
        },
    },
}


def _ensure(con):
    # Additive table, same SQL on SQLite and PostgreSQL. Caller holds the
    # existing global gameplay write lock, including on first deployment.
    con.execute("""CREATE TABLE IF NOT EXISTS web_adventure_progress (
        season_key TEXT NOT NULL, player_id BIGINT NOT NULL, chapter TEXT NOT NULL,
        epoch TEXT NOT NULL, revision INTEGER NOT NULL, state_json TEXT NOT NULL,
        last_request TEXT NOT NULL, last_signature TEXT NOT NULL,
        PRIMARY KEY (season_key, player_id, chapter))""")


def _fresh():
    return {"scene": "office", "items": [], "evidence": [], "flags": [],
            "dialogue": None, "complete": False, "message": "Search the room to begin."}


def _load(con, season, user, *, create):
    row = con.execute("""SELECT epoch,revision,state_json,last_request,last_signature
        FROM web_adventure_progress WHERE season_key=? AND player_id=? AND chapter=?""",
                      (season, user, CHAPTER)).fetchone()
    if row is not None:
        return row[0], row[1], json.loads(row[2]), row[3], row[4]
    if not create:
        return None
    epoch = secrets.token_hex(16)
    state = _fresh()
    con.execute("""INSERT INTO web_adventure_progress
        (season_key,player_id,chapter,epoch,revision,state_json,last_request,last_signature)
        VALUES(?,?,?,?,0,?,'','')""", (season, user, CHAPTER, epoch, json.dumps(state)))
    return epoch, 0, state, "", ""


def _has(state, requirements):
    facts = set(state["flags"]) | {"i:" + x for x in state["items"]} | {
        "e:" + x for x in state["evidence"]}
    return all(x in facts for x in requirements)


def _rule(state, action, target):
    scene = SCENES[state["scene"]]
    if action == "choose" and state["dialogue"]:
        rule = DIALOGUES[state["dialogue"]]["choices"].get(target)
    elif action == "inspect" and not state["dialogue"]:
        rule = scene["targets"].get(target)
    elif action == "use" and not state["dialogue"] and target in state["items"]:
        rule = scene["uses"].get(target)
    else:
        rule = None
    if rule is None or not _has(state, rule.get("requires", [])):
        raise ValueError("That action is not available here. Check your evidence or satchel.")
    for flag, replacement in rule.get("when", {}).items():
        if _has(state, [flag]):
            return {**rule, **replacement}
    return rule


def _apply(state, rule):
    for field, effect in (("items", "give"), ("evidence", "evidence")):
        for value in rule.get(effect, []):
            if value not in state[field]:
                state[field].append(value)
    if rule.get("flag") and rule["flag"] not in state["flags"]:
        state["flags"].append(rule["flag"])
    if rule.get("move"):
        state["scene"] = rule["move"]
        state["dialogue"] = None
    if rule.get("dialogue"):
        state["dialogue"] = rule["dialogue"]
    if rule.get("close") or rule.get("complete"):
        state["dialogue"] = None
    if rule.get("complete"):
        state["complete"] = True
    state["message"] = rule["text"]


def _view(record, day, phase, *, repeated=False):
    epoch, revision, state, _, _ = record
    scene = SCENES[state["scene"]]
    dialogue = None
    if state["dialogue"]:
        d = DIALOGUES[state["dialogue"]]
        dialogue = {"speaker": d["speaker"], "text": d["text"],
                    "choices": [{"key": k, "label": r["label"]}
                                for k, r in d["choices"].items()
                                if _has(state, r.get("requires", []))]}
    return {"chapter": CHAPTER, "title": "The Missing Winter Dispatch",
            "day": day, "phase": phase, "epoch": epoch, "revision": revision,
            "scene": {"key": state["scene"], "title": scene["title"],
                      "description": scene["description"], "art": scene["art"],
                      "hotspots": [{"key": k, "label": r["label"], "x": r["x"], "y": r["y"]}
                                   for k, r in scene["targets"].items()
                                   if _has(state, r.get("requires", []))]},
            "dialogue": dialogue, "message": state["message"], "complete": state["complete"],
            "inventory": [{"key": k, "label": ITEMS[k][0], "description": ITEMS[k][1],
                           "use": (scene["uses"][k]["label"] if k in scene["uses"]
                                   and _has(state, scene["uses"][k].get("requires", []))
                                   else None)}
                          for k in state["items"]],
            "evidence": [{"label": EVIDENCE[k][0], "text": EVIDENCE[k][1]}
                         for k in state["evidence"]],
            "souvenir": "Winter Dispatch Detective" if state["complete"] else None,
            "repeated": repeated}


def adventure_view(store, season, user, now):
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        day = WinterFunEngine._current(con, season, user, now, active=False)
        state = store._make_season(con.execute("SELECT * FROM season_state WHERE season_key=?",
                                              (season,)).fetchone())
        phase = state.phase(now)
        _ensure(con)
        record = _load(con, season, user, create=phase == "live" and day is not None)
        return _view(record, day, phase) if record else None


def adventure_action(store, season, user, now, *, day, epoch, revision, action, target, request):
    with store.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        current = WinterFunEngine._current(con, season, user, now, active=True)
        if current != day:
            raise ValueError("The event day changed. Refresh the adventure.")
        _ensure(con)
        record = _load(con, season, user, create=False)
        if not record or record[0] != epoch:
            raise ValueError("This adventure was reset. Refresh to start again.")
        _, rev, state, last, signature = record
        incoming = json.dumps([revision, action, target], separators=(",", ":"))
        if request == last:
            if incoming != signature:
                raise ValueError("Request already used for another adventure action.")
            return _view(record, day, "live", repeated=True)
        if revision != rev:
            raise ValueError("Adventure changed in another tab. Refresh before continuing.")
        if state["complete"]:
            raise ValueError("This adventure is already complete.")
        rule = _rule(state, action, target)
        _apply(state, rule)
        con.execute("""UPDATE web_adventure_progress SET revision=?,state_json=?,
            last_request=?,last_signature=? WHERE season_key=? AND player_id=? AND chapter=?""",
                    (rev + 1, json.dumps(state), request, incoming, season, user, CHAPTER))
        return _view((epoch, rev + 1, state, request, incoming), day, "live")

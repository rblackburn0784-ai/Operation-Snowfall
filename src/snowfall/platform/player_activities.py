"""Private player activities using the existing Discord engines.

Explicit allowlisted fields prevent undiscovered clue text and answers leaking
through the raw MysterySnapshot dataclass. No alternate reward implementation.
"""
from dataclasses import asdict

from snowfall.services.achievements import AchievementEngine
from snowfall.services.economy import EconomyEngine, ITEM_NAMES, DAILY_USE_CAPS
from snowfall.services.experience import headquarters
from snowfall.services.mysteries import MysteryEngine, MAX_GUESSES, SECRET_CHOICES
from snowfall.services.winter_fun import WinterFunEngine, ENCOUNTERS, ENCOUNTER_CHOICES


def activities_view(store, season, user, now):
    mystery = MysteryEngine(store).snapshot(season, user, now)
    shop = WinterFunEngine(store).shop(season, user, now)
    inventory = EconomyEngine(store).inventory(season, user, now)
    hq = headquarters(store, season, user, now)
    cabinet = AchievementEngine(store).cabinet(season, user)
    case = mystery.case
    day = mystery.day
    ordinary = None
    if day is not None:
        title, scene, _souvenir = ENCOUNTERS[day - 1]
        ordinary = {"title": title, "scene": scene,
                    "completed": asdict(shop.encounter) if shop.encounter else None,
                    "choices": [{"key": key, "label": value[0]}
                                for key, value in ENCOUNTER_CHOICES.items()]}
    investigation = None
    if case:
        investigation = {
            "title": case.title, "scene": case.scene,
            "clues": [{"key": clue.key, "label": clue.label, "found": clue.found,
                       "text": clue.text if clue.found else None} for clue in mystery.clues],
            "suspects": [{"key": key, "label": label} for key, label in case.suspects],
            "guesses": mystery.guesses, "max_guesses": MAX_GUESSES,
            "solved": mystery.solved, "locked": mystery.locked,
            "conclusion": case.conclusion if mystery.solved else None,
            "secret": asdict(mystery.secret) if mystery.secret else None,
            "secret_ready": mystery.secret_ready,
            "secret_title": case.secret_title if mystery.secret_ready or mystery.secret else None,
            "secret_scene": case.secret_scene if mystery.secret_ready or mystery.secret else None,
            "secret_choices": [{"key": key, "label": value[0]}
                               for key, value in SECRET_CHOICES.items()] if mystery.secret_ready else [],
        }
    return {
        "player_id": str(user), "day": day, "phase": mystery.phase,
        "case": investigation, "encounter": ordinary,
        "history": [asdict(entry) for entry in mystery.history
                    if day is not None and entry.day <= day],
        "inventory": asdict(inventory),
        "item_names": dict(ITEM_NAMES), "use_caps": dict(DAILY_USE_CAPS),
        "quests": [asdict(q) for q in hq.quests],
        "daily_gift": hq.daily_gift, "bonus_gift": hq.bonus_gift,
        "equipped_title": cabinet.equipped_title,
        "titles": [{"key": t.key, "label": t.title} for t in cabinet.trophies if t.unlocked],
    }


def perform_activity(store, season, user, action, item, day, interaction, now):
    # All timed requests carry the displayed day. A stale browser must never
    # spend a new day's attempt when replaying yesterday's unconfirmed action.
    state = store.season(season)
    if state is None:
        raise ValueError("Event not configured.")
    if action != "title" and (day is None or state.day(now) != day):
        raise ValueError("The event day changed. Refresh Winter Activities first.")
    economy = EconomyEngine(store)
    mystery = MysteryEngine(store)
    if action == "clue":
        clue, repeated = mystery.investigate(season, user, item, interaction, now)
        return {"message": clue.text, "repeated": repeated}
    if action == "accuse":
        result = mystery.accuse(season, user, item, interaction, now)
        return {"message": result.message, "repeated": result.repeated}
    if action == "secret":
        result = mystery.secret(season, user, item, interaction, now)
        return {"message": result.souvenir, "repeated": result.repeated}
    if action == "encounter":
        result = WinterFunEngine(store).encounter(season, user, interaction, now, item)
        return {"message": result.souvenir, "repeated": result.repeated}
    if action == "quest":
        result = economy.claim_quest(season, user, item, now)
    elif action == "gift":
        gift = economy.present(season, user, interaction, now, source=item)
        return {"message": f"Present: {gift.amount} {gift.actual_reward}.",
                "repeated": gift.repeated}
    elif action == "use":
        result = economy.use(season, user, item, interaction, now)
    elif action == "guard":
        result = economy.guard(season, user, item, interaction, now)
    elif action == "title":
        return {"message": "Title equipped: " + AchievementEngine(store).equip(season, user, item)}
    else:
        raise ValueError("Unknown activity.")
    return {"message": result.text, "repeated": result.repeated}

"""v2.9.9e — Christmas Trivia server game, timers, secrecy and Discord isolation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import random

import pytest

from snowfall.db.store import Store
from snowfall.platform.trivia_arcade import (
    BANK, MAX_QUESTIONS, PATTERN, QUESTION_MS, TOTAL_MS,
    ChristmasTriviaEngine, _make_deck, install_trivia_schema,
)
from snowfall.services.social_arcade import SocialArcadeEngine

SEASON = "trivia-qa"
START = datetime(2026, 12, 20, 18, tzinfo=timezone.utc)


def when(ms):
    return START + timedelta(milliseconds=ms)


@pytest.fixture
def quiz(tmp_path):
    store = Store(tmp_path / "trivia.sqlite3")
    store.initialize()
    store.ensure_season(SEASON, START)
    for user, name in ((101, "Quizmaster"), (202, "FestiveRival")):
        store.register(SEASON, user, name, "Chicago", START-timedelta(days=1))
    store.transition(SEASON, 900, "start", START, "Trivia QA")
    with store.connect() as con:
        install_trivia_schema(con)
        install_trivia_schema(con)
    assert store.schema_version() == 11
    return ChristmasTriviaEngine(store, SEASON, random.Random(42)), store


def server_deck(store, sid):
    with store.connect() as con:
        return json.loads(con.execute(
            "SELECT deck_json FROM web_arcade_trivia_sessions WHERE session_id=?",
            (sid,)).fetchone()[0])


def test_question_deck_has_15_varying_puzzles_three_levels_and_private_keys(quiz):
    engine, store = quiz
    deck = _make_deck(random.Random(42))
    assert len(deck) == MAX_QUESTIONS == 15
    assert [q["kind"] for q in deck] == list(PATTERN)*3
    assert [q["level"] for q in deck] == [1]*5 + [2]*5 + [3]*5
    assert [q["limit_ms"] for q in deck] == [QUESTION_MS[i//5]
                                               for i in range(15)]
    assert len({q["id"] for q in deck}) == 15
    assert all(q["correct"] in q["options"] for q in deck if q["kind"] == "gift")
    assert all(sorted(q["tiles"]) == sorted(q["correct"])
               for q in deck if q["kind"] == "scramble")
    assert all(q["correct"] != "".join(q["tiles"])
               for q in deck if q["kind"] == "scramble")
    assert all(len(bank)>=10 for bank in BANK)
    ready = engine.start(101, now=START)
    assert ready["mode"] == "trivia" and ready["status"] == "paused"
    assert ready["practice"] and not ready["competitive"]
    assert ready["step"] == 0 and ready["round"] == 1
    assert ready["question_remaining_ms"] == 16_000
    assert ready["total_questions"] == 15
    assert ready["score"] == ready["correct"] == 0
    assert ready["history"] == []
    assert not any(k in ready["question"] for k in ("correct", "answer", "explanation"))
    assert "deck" not in ready
    assert engine.start(101, now=START)["session_id"] == ready["session_id"]
    with pytest.raises(ValueError, match="unavailable"):
        engine.session(202, ready["session_id"], now=START)


def test_all_15_perfect_answers_score_100_and_never_touch_discord(quiz):
    engine, store = quiz
    sid = engine.start(101, now=START)["session_id"]
    deck = server_deck(store, sid)
    assert engine.control(101, sid, "resume", now=when(100))["status"] == "active"
    for i, q in enumerate(deck):
        turn = engine.answer(
            101, sid, i, q["correct"], f"trivia-perfect-{i:02d}",
            now=when(600+i*520))
        assert turn["step"] == i+1
        assert turn["last_answer"]["verdict"] == "correct"
        assert turn["last_answer"]["points"] >= 7
        assert turn["streak"] == i+1
        assert turn["correct"] == i+1 and turn["wrong"] == turn["timeouts"] == 0
        if i<14:
            assert turn["question"]["id"] == deck[i+1]["id"]
            assert "correct" not in turn["question"]
            assert turn["history"] == []
    assert turn["status"] == "finished" and turn["score"] == 100
    assert turn["result"].startswith("NORTH POLE QUIZ")
    assert len(turn["history"]) == 15
    assert turn["question"] is None and turn["best_streak"] == 15
    assert turn["history"][-1]["answer"] == deck[-1]["correct"]
    record = engine.record(101, now=when(10000))
    assert record["personal_best"] == 100 and record["best_correct"] == 15
    assert record["finished_runs"] == 1
    assert engine.start(101, now=when(10_100))["session_id"] != sid
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM web_arcade_trivia_answers").fetchone()[0] == 15
        assert con.execute("SELECT COUNT(*) FROM social_arcade_runs").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM score_ledger").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM prize_awards").fetchone()[0] == 0
    assert SocialArcadeEngine(store).lobby(SEASON, 101, when(10000)).record(
        "trivia").attempts_today == 0


def test_wrong_answer_replay_account_ownership_and_step_guards(quiz):
    engine, store = quiz
    ready = engine.start(101, now=START)
    sid = ready["session_id"]
    deck = server_deck(store, sid)
    q = deck[0]
    bad = next(option for option in q["options"] if option != q["correct"])
    with pytest.raises(ValueError, match="paused"):
        engine.answer(101, sid, 0, bad, "prestart-trivia", now=when(100))
    engine.control(101, sid, "resume", now=when(100))
    wrong = engine.answer(101, sid, 0, bad, "trivia-wrong-00001", now=when(1100))
    assert wrong["step"] == 1 and wrong["score"] == 0
    assert wrong["wrong"] == 1 and wrong["streak"] == 0
    assert wrong["last_answer"]["answer"] == q["correct"]
    assert wrong["last_answer"]["selected"] == bad
    assert wrong["history"] == []
    duplicate = engine.answer(
        101, sid, 0, bad, "trivia-wrong-00001", now=when(2000))
    assert duplicate["repeated"] and duplicate["score"] == 0
    with pytest.raises(ValueError, match="belongs"):
        engine.answer(202, sid, 0, bad, "trivia-wrong-00001", now=when(2100))
    with pytest.raises(ValueError, match="belongs"):
        engine.answer(101, sid, 0, q["correct"], "trivia-wrong-00001",
                      now=when(2200))
    with pytest.raises(ValueError, match="out of order"):
        engine.answer(101, sid, 8, bad, "trivia-future-0001", now=when(2300))
    with pytest.raises(ValueError, match="offered"):
        engine.answer(101, sid, 1, "ClientForcesWin", "trivia-forge-0001",
                      now=when(2300))
    assert engine.session(101, sid, now=when(2500))["step"] == 1
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM web_arcade_trivia_answers").fetchone()[0] == 1


def test_automatic_question_timeouts_are_server_owned(quiz):
    engine, store = quiz
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(100))
    first = engine.session(101, sid, now=when(16_150))
    assert first["step"] == 1
    assert first["timeouts"] == 1 and first["wrong"] == 0
    assert first["last_answer"]["verdict"] == "timeout"
    assert "correct" not in first["question"]
    with pytest.raises(ValueError, match="out of order"):
        engine.answer(101, sid, 0, "Reindeer", "expired-0001",
                      now=when(16_300))
    done = engine.session(101, sid, now=when(TOTAL_MS+300))
    assert done["status"] == "finished"
    assert done["step"] == 15 and done["timeouts"] == 15
    assert done["score"] == 0 and done["streak"] == 0
    assert done["elapsed_ms"] == TOTAL_MS
    assert len(done["history"]) == 15
    assert all(event["verdict"] == "timeout" for event in done["history"])
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM web_arcade_trivia_answers").fetchone()[0] == 0
    assert engine.start(101, now=when(TOTAL_MS+500))["session_id"] != sid


def test_scrambled_letter_answers_must_use_every_tile(quiz):
    engine, store = quiz
    sid = engine.start(101, now=START)["session_id"]
    deck = server_deck(store, sid)
    engine.control(101, sid, "resume", now=when(100))
    for i in range(4):
        engine.answer(101, sid, i, deck[i]["correct"],
                      f"quiz-before-tiles-{i}", now=when(700+i*500))
    q = deck[4]
    assert q["kind"] == "scramble"
    with pytest.raises(ValueError, match="each available letter"):
        engine.answer(101, sid, 4, "UNFAIR", "scramble-forgery-0001",
                      now=when(3000))
    with pytest.raises(ValueError, match="each available letter"):
        engine.answer(101, sid, 4, q["correct"]+"X",
                      "scramble-extra-letter", now=when(3000))
    reverse = q["correct"][::-1]
    result = engine.answer(101, sid, 4, reverse, "scramble-wrong-word",
                           now=when(3200))
    assert result["step"] == 5 and result["round"] == 2
    assert result["last_answer"]["verdict"] == "wrong"
    assert result["last_answer"]["answer"] == q["correct"]
    assert result["streak"] == 0
    assert result["history"] == []


def test_pause_resume_freezes_deadlines_and_ends_early(quiz):
    engine, store = quiz
    sid = engine.start(101, now=START)["session_id"]
    engine.control(101, sid, "resume", now=when(200))
    paused = engine.control(101, sid, "pause", now=when(5200))
    assert paused["status"] == "paused" and paused["elapsed_ms"] == 5000
    assert paused["question_remaining_ms"] == 11_000
    assert engine.session(101, sid, now=when(60_000))["question_remaining_ms"] == 11_000
    assert engine.control(101, sid, "pause", now=when(65_000))["status"] == "paused"
    engine.control(101, sid, "resume", now=when(70_000))
    assert engine.session(101, sid, now=when(80_000))["step"] == 0
    assert engine.session(101, sid, now=when(82_000))["step"] == 1
    finished = engine.control(101, sid, "finish", now=when(82_100))
    assert finished["status"] == "finished"
    assert finished["timeouts"] == 1
    assert engine.record(101, now=when(82_200))["finished_runs"] == 1
    assert engine.control(101, sid, "finish", now=when(82_200))["status"] == "finished"


def test_concurrent_same_step_only_one_awarded(quiz):
    engine, store = quiz
    sid = engine.start(101, now=START)["session_id"]
    q = server_deck(store, sid)[0]
    engine.control(101, sid, "resume", now=when(100))
    def submit(index):
        try:
            return engine.answer(101, sid, 0, q["correct"],
                                 f"trivia-parallel-{index}", now=when(700))
        except ValueError as e:
            return e
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert engine.session(101, sid, now=when(800))["step"] == 1
    with store.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM web_arcade_trivia_answers").fetchone()[0] == 1


def test_api_auth_csrf_default_off_and_browser_cannot_set_points(monkeypatch):
    from unittest.mock import Mock

    from fastapi.testclient import TestClient
    from snowfall.platform.api import create_app
    from test_v293_platform import FakeIdentity, fake_settings

    identity, game = FakeIdentity(), Mock()
    game.trivia_start.return_value = {"session_id": "a"*32}
    game.trivia_answer.return_value = {"score": 7}
    with TestClient(create_app(fake_settings(), identity=identity, game=game),
                    base_url="https://snowfall.example") as client:
        assert client.post("/v1/game/arcade/trivia/start").status_code == 401
        token, csrf = identity.new_session(101)
        client.cookies.set("snowfall_session", token)
        assert client.post("/v1/game/arcade/trivia/start").status_code == 403
        headers = {"X-Snowfall-CSRF": csrf}
        assert client.post("/v1/game/arcade/trivia/start",
                           headers=headers).status_code == 503
        monkeypatch.setenv("SNOWFALL_ARCADE_V299E_ENABLED", "1")
        assert client.post("/v1/game/arcade/trivia/start",
                           headers=headers).status_code == 200
        body = {"session_id": "a"*32, "step": 0, "answer": "Reindeer"}
        assert client.post("/v1/game/arcade/trivia/answer", json=body,
                           headers=headers).status_code == 400
        headers["Idempotency-Key"] = "quiz-client-answered-001"
        assert client.post("/v1/game/arcade/trivia/answer", json=body,
                           headers=headers).status_code == 200
        assert game.trivia_answer.call_args.args[:4] == (
            101, "a"*32, 0, "Reindeer")
        assert client.post("/v1/game/arcade/trivia/answer",
                           json={**body, "score": 1000,
                                 "correct": True, "difficulty": 99},
                           headers=headers).status_code == 200
        assert game.trivia_answer.call_args.args[:4] == (
            101, "a"*32, 0, "Reindeer")

# v2.9.9e — Christmas Trivia: Full Interactive Game

**Isolated QA web release:** completes the five full Arcade 2.0 mini-games,
reusing the existing responsive canvas, input, optional sound and
pause/resume session host. The original Discord arcade, daily starts,
resources, passports, seasonal rankings and prize records are unchanged.

## Gameplay

The player opens **Winter Arcade → Play Christmas Trivia · QA**, presses
**Start / resume**, and enters a 15-question, three-level quiz show:

1. **Snowy Warmup:** 5 easier questions, 16 seconds each.
2. **Workshop Rush:** 5 medium questions, 14 seconds each.
3. **North Pole Finale:** 5 harder questions, 12 seconds each.

The 15-question sequence mixes three genuinely interactive challenge types
in each level:

- **Mystery Presents:** four festively wrapped, touch/clickable answer cards.
- **True or False:** two large, high-contrast Christmas quiz cards.
- **Letter Lock:** rearrange shuffled letter tiles into a festive word,
  correcting mistakes with Undo or Clear before confirming.

Players can use mouse, touchscreen or keyboard. For choice and True/False,
press 1–4, use arrow keys to select, or press Enter to confirm. For letter
locks, press the numbered tile keys, Backspace to undo, Escape to clear and
Enter to check. All modes include large on-screen controls and responsive
mobile layout.

Correct answers earn server-computed points; faster answers and consecutive
correct answers increase the bonus. A wrong answer resets the streak.
Expired questions are marked as timeouts automatically and the game moves
on. Maximum practice score: **100**. End results include correct answers,
explanations, total correct, missed, timeouts, best streak and personal best.

Each round shuffles questions from a bank of Christmas traditions, music,
literature, decorations and seasonal popular culture; the server selects
the questions and checks answers. Players can play unlimited unranked
practice rounds without using Discord daily arcade starts.

## Integrity and replay safety

The server stores the whole selected quiz deck and its answers **in the
database only**. The browser receives the current question and available
answer cards/letter tiles, not future questions or answer keys.
The correct answer and explanation are revealed only after that question
has been answered or timed out.

The server enforces question-specific timers using active elapsed playtime;
page refreshes and navigation cannot reset time, and pausing freezes
the question countdown. HTTP sessions are account-bound, CSRF-protected
and feature-gated. Answer submissions require a stable idempotency key,
next expected question index and an offered answer or exact tile multiset.
Replays cannot score again or change a submitted answer; concurrent
submissions cannot double-award points. Score, streak, timeout and
question progression are never client-authoritative.

Results are held only in web_arcade_trivia_sessions and
web_arcade_trivia_answers, not classic social_arcade_runs, score_ledger,
prize_awards or economy data. No official prizes or City Cup records
are affected.

## Explicit QA activation — OFF by default

**Pushing the code does not install tables or activate Trivia on Railway.**

1. Back up the isolated Snowfall-Web-QA PostgreSQL database.
2. In a protected staging shell, use the private DSN for exactly
   **/snowfall_web_qa**, never the imported **/railway** database.
   Set SNOWFALL_API_SEASON_KEY=web-qa-2026.
3. Run the guarded additive migration:

       python -m snowfall.platform.arcade_migration --confirm WEB_QA_ONLY

   The installer verifies both the exact QA database and the existing
   project/season marker, then adds the Trivia tables and indexes
   without changing the canonical game schema version.
4. Verify web_arcade_trivia_sessions and web_arcade_trivia_answers exist
   and other game tables are intact.
5. Set **SNOWFALL_ARCADE_V299E_ENABLED=1** on the **QA web service only**,
   then redeploy it. All other arcade games have their own flags.
6. Log in through an eligible Underworld QA account; test all three
   challenge formats, mouse/touch/keyboard, question timer, automatic
   expiry, score/streak calculations, sound opt-in, pause, refresh/resume,
   retries, completed result and replay.

Do not enable on the Discord worker or live/prod web until the staged
cross-platform checks and manual device QA have been accepted.
The server does not automatically run the schema installer at startup.

## Automated checks

- python -m pytest -q tests/test_v299e_trivia.py
- python -m pytest -q tests/test_v299_arcade_postgres.py
- node --check src/snowfall/platform/static/arcade-trivia-v299e.js
- node --test tests/test_v299e_trivia_browser.mjs
- Full GitHub CI: Linux Python 3.12/3.13, Windows Python 3.13,
  all existing browser regressions and isolated PostgreSQL integration.

## What's next

**v2.9.9f — Arcade Hub 2.0:** unify the five completed games behind an
intuitive launch screen, show practice records and session states,
simplify mobile navigation, and test their coexistence. Once that
foundation is solid, v2.9.9g and v2.9.9h focus on presentation,
balancing, security and staged release readiness.

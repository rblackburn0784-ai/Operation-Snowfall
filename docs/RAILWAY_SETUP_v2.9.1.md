# Deploy Operation Snowfall v2.9.1 to Railway

This version hosts the **existing Discord-only bot**. It is not yet a web
frontend or a shared database. Underworld and web account linking are v2.9.2+.

## A. Prepare your repository

1. Install the v2.9.1 release into your existing Operation-Snowfall project.
2. Run `python -m pip install -e ".[dev]"`, `python -m ruff check src tests
   --select E4,E7,E9,F`, then `python -m pytest -q`.
3. Make a safe offline/SQLite-online backup of any valuable current database.
4. Commit the changed source, Dockerfile, documentation, `.dockerignore` and
   tests to GitHub (`main` once checks are green). Never commit secrets,
   `config.toml`, `.env`, SQLite files, or the extracted installer directory.

## B. Create the Railway bot service

1. Open Railway and create a new project (or a separately managed service
   within a project if you already host Underworld there).
2. Choose **Deploy from GitHub Repo**: `rblackburn0784-ai/Operation-Snowfall`.
   Select the correct branch and root `/`. Railway uses the `Dockerfile`.
3. Call the service `snowfall-bot`. Use **one instance only**; do not add a
   public domain, HTTP port, HTTP healthcheck path or a pre-deploy DB command.
   Discord opens an outbound gateway connection; it is not an HTTP server.
4. **Before the first successful deployment**, attach a persistent Railway
   **Volume** to this service at exactly `/data`. The `RAILWAY_VOLUME_MOUNT_PATH`
   variable is injected automatically by Railway. Without a volume, this
   release intentionally refuses to launch and cannot lose SQLite state on a
   restart or deploy. The volume must be attached to the bot service itself.
5. In the service **Variables** tab, add:

   ```env
   DISCORD_TOKEN=<secret token from Discord Developer Portal>
   SNOWFALL_GUILD_ID=<snowfall event server ID>
   SNOWFALL_ADMIN_USER_IDS=<your Discord user ID, comma-separated with Kat/staff as needed>
   SNOWFALL_STAFF_ROLE_IDS=
   SNOWFALL_ANNOUNCEMENT_CHANNEL_ID=<announcements channel ID or 0>
   SNOWFALL_LEADERBOARD_CHANNEL_ID=<leaderboard channel ID or 0>
   SNOWFALL_STARTS_AT_UTC=<real agreed UTC ISO date-time, e.g. 2026-12-20T19:00:00+00:00>
   SNOWFALL_SEASON_KEY=christmas-2026
   SNOWFALL_EVENT_NAME=Operation Snowfall
   ```

   **The example date is NOT the agreed event time.** Set the actual host-
   approved kickoff. Avoid adding `SNOWFALL_DATA_DIR`; the volume controls it.
   All IDs must be real numeric Discord IDs. Do not put a token in GitHub.

6. In Railway service settings, set restart policy to **On Failure** (or your
   preferred monitored policy), and keep a single replica. Apply variable
   changes and redeploy. Do not add a manual start-command override; the
   Dockerfile already defines the command.
7. Review Deploy Logs for `Starting Discord-only Snowfall worker` followed by
   the existing `[PRODUCTION] Connected as ...` readiness line. Verify slash
   commands in your dedicated server and use the existing host test controls.
8. Stop the bot currently running in PyCharm, and keep it stopped while
   Railway runs the same live Discord application token.

## C. Existing local player data? Preserve it before switching

If you have existing **live** SQLite state on your PC, **do not let Railway
create an independent empty game and then replace it while the bot is running**.

1. Stop the PyCharm bot. Create a WAL-aware, consistent backup from the
   existing project's normal backup tool: `python bot.py --backup-now` (while
   config.toml and local token are still present), or use Python's SQLite
   online backup API. Locate the resulting `snowfall-....sqlite3` and verify
   it opens and `PRAGMA quick_check` returns `ok`.
2. On Railway, stop the deployment/service before transferring an existing
   database. Upload a *verified standalone* backup SQLite file into the
   volume at `/snowfall.sqlite3`. Railway's current CLI supports
   `railway volume files upload ./snowfall.sqlite3 /snowfall.sqlite3` after
   selecting/linking the correct project, environment and volume. No `-wal`
   or `-shm` file should accompany the backup.
3. Restart the service. The entrypoint checks the database and backs it up
   before handing control to the app. Confirm player counts and scores with
   the organiser. If transferring an existing production event, perform a
   careful cutover and recovery drill; NEVER have local and Railway workers
   edit different copies as if they were one game.

## D. Persistence and operational safety

- SQLite database: `/data/snowfall.sqlite3` (persistent).
- Daily and prestart backups: `/data/backups/` (persistent).
- Disposable practice databases: `/data/practice/` (persistent during a test;
  cleaned up on stop/restart as in the existing bot).
- Add Railway **volume backups** in Railway and export an off-platform copy;
  backups on the same volume do not protect against volume loss.
- Railway volumes are single-service, single-replica and may cause a brief
  restart/deploy interruption. The later PostgreSQL release removes the
  SQLite single-writer design and will support an API/web service.
- For command-level configuration checks, a deployment shell can run
  `python -m snowfall.railway --check`. It verifies configuration, volume
  mount and SQLite integrity but cannot prove the Discord token is valid.
- If the worker fails startup, logs explain missing variables, volume or
  malformed UTC date without printing the token.

## E. Common failures

- **Volume not detected**: attach a Railway volume at `/data` to this bot
  service; do not set `/tmp` as the data directory.
- **Discord 403 Missing Access**: wrong Discord guild ID, bot not installed in
  event server, or missing applications.commands scope.
- **No slash commands**: confirm the correct dedicated guild and the bot
  installation; commands are guild-scoped.
- **Database integrity failed**: stop deployment; restore a verified backup,
  do not delete a live DB to force startup.
- **Duplicate worker**: ensure Railway has a single replica, and your
  PyCharm instance is stopped. Linux volume lock helps only when workers
  share the exact same volume.

Reference docs: https://docs.railway.com/volumes/reference ,
https://docs.railway.com/variables and https://docs.railway.com/cli/volume .

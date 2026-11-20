"""Opt-in PostgreSQL storage adapter for the unchanged Snowfall game engine.

Every data-changing engine already uses Store.connect(); this module supplies a
PostgreSQL-compatible sqlite-like connection. No web API or new identity model yet.
A fully migrated v11 schema is required; this adapter does not auto-create tables.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from snowfall.db.store import DB_VERSION, Store

# A global transaction advisory lock intentionally serializes game writes across
# all future workers. It is acquired for every modifying statement or an explicit
# BEGIN IMMEDIATE. Never use autocommit, or this lock would be ineffective.
LOCK_KEY = 2026122002912


def _psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('Install the PostgreSQL extra: pip install -e ".[postgres]"') from exc
    return psycopg


class CompatibleRow:
    """sqlite3.Row-compatible access by column name or position."""
    def __init__(self, names: tuple[str, ...], values: tuple[Any, ...]):
        self._names = names
        self._values = tuple(_sqlite_value(value) for value in values)
        self._by_name = {}
        for name, value in zip(names, self._values):
            self._by_name.setdefault(name, value)

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._by_name[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._names)

    def items(self):
        return self._by_name.items()


def _sqlite_value(value):
    if isinstance(value, Decimal):
        return int(value) if value == int(value) else float(value)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def compatible_row_factory(cursor):
    """Return sqlite-like rows, including for commands with no result columns.

    Psycopg invokes the factory after INSERT/UPDATE/DELETE and ON CONFLICT
    DO NOTHING even though their cursor.description is None. The callable
    is not normally used for those commands, but must still be constructible.
    """
    description = cursor.description
    cols = tuple(field.name for field in description) if description else ()
    return lambda values: CompatibleRow(cols, values)


def _scalar_function(sql: str, function: str, replacement: str) -> str:
    """Translate SQLite scalar MIN/MAX with >=2 arguments, never SQL aggregates.

    A nested COALESCE can contain commas, so count arguments at depth zero.
    """
    matcher = re.compile(r'\b' + function + r'\s*\(', flags=re.IGNORECASE)
    output = []
    pos = 0
    while match := matcher.search(sql, pos):
        start = match.end()
        depth, commas, i = 0, 0, start
        quote = None
        while i < len(sql):
            ch = sql[i]
            if quote:
                if ch == quote:
                    if i + 1 < len(sql) and sql[i + 1] == quote:
                        i += 1
                    else:
                        quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == '(':
                depth += 1
            elif ch == ')':
                if depth == 0:
                    break
                depth -= 1
            elif ch == ',' and depth == 0:
                commas += 1
            i += 1
        output.append(sql[pos:match.start()])
        output.append(replacement + '(' if commas else sql[match.start():start])
        pos = start
    output.append(sql[pos:])
    return ''.join(output)


def translate_sql(statement: str) -> str:
    """Convert vetted SQLite game queries into PostgreSQL SQL placeholders."""
    query = re.sub(r'\bINSERT\s+OR\s+IGNORE\s+INTO\b', 'INSERT INTO', statement, flags=re.I)
    if query != statement:
        query = query.strip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    query = _scalar_function(query, 'MIN', 'LEAST')
    query = _scalar_function(query, 'MAX', 'GREATEST')
    # Respect quoted literal question marks and SQL comments when replacing
    # SQLite parameter markers.
    parts, quote, i = [], None, 0
    while i < len(query):
        char = query[i]
        if quote:
            parts.append(char)
            if char == quote:
                if i + 1 < len(query) and query[i + 1] == quote:
                    parts.append(query[i + 1])
                    i += 1
                else:
                    quote = None
        elif char in "'\"":
            quote = char
            parts.append(char)
        elif query.startswith('--', i):
            end = query.find('\n', i)
            if end == -1:
                parts.append(query[i:])
                break
            parts.append(query[i:end+1])
            i = end
        elif query.startswith('/*', i):
            end = query.find('*/', i + 2)
            if end == -1:
                raise ValueError('Unclosed SQL block comment')
            parts.append(query[i:end+2])
            i = end + 1
        elif char == '?':
            parts.append('%s')
        else:
            parts.append(char)
        i += 1
    return ''.join(parts)


class StaticCursor:
    def __init__(self, values=()):
        self.values = tuple(values)
        self.rowcount = -1
        self.lastrowid = None

    def fetchone(self):
        return self.values[0] if self.values else None

    def fetchall(self):
        return list(self.values)

    def __iter__(self):
        return iter(self.values)


class CursorAdapter:
    def __init__(self, cursor, *, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)


class ConnectionAdapter:
    def __init__(self, connection):
        self._connection = connection
        self._locked = False

    def _lock(self):
        if not self._locked:
            with self._connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_KEY,))
            self._locked = True

    def execute(self, sql: str, parameters=()):
        command = sql.strip().rstrip(';')
        command_upper = command.upper()
        if command_upper == 'BEGIN IMMEDIATE':
            self._lock()
            return StaticCursor()
        if command_upper in ('BEGIN', 'BEGIN TRANSACTION'):
            # psycopg opens a transaction implicitly; a nested SQL BEGIN would
            # otherwise produce a PostgreSQL warning or driver error.
            return StaticCursor()
        if command_upper.startswith('PRAGMA '):
            raise RuntimeError('Unsupported SQLite PRAGMA on PostgreSQL: ' + command[:60])
        if re.match(r'^(?:INSERT|UPDATE|DELETE|REPLACE)\b', command_upper):
            self._lock()
        pg_query = translate_sql(sql)
        try:
            cursor = self._connection.execute(pg_query, parameters)
            lastrowid = None
            if re.match(r'^\s*INSERT\s+INTO\s+wire_submissions\b', pg_query, re.I):
                with self._connection.cursor() as sequence_cursor:
                    sequence_cursor.execute("SELECT currval(pg_get_serial_sequence('wire_submissions', 'id'))")
                    lastrowid = sequence_cursor.fetchone()[0]
            return CursorAdapter(cursor, lastrowid=lastrowid)
        except _psycopg().IntegrityError as exc:
            # Existing registration and economy code catches sqlite3.IntegrityError.
            raise sqlite3.IntegrityError(str(exc)) from exc


class PostgresStore(Store):
    """Use a verified imported PostgreSQL schema, without modifying SQLite Store."""

    backend = 'postgres'

    def __init__(self, dsn: str, *, practice_root: Path):
        if not (dsn.startswith('postgresql://') or dsn.startswith('postgres://')):
            raise ValueError('SNOWFALL_DATABASE_URL must be a PostgreSQL URL')
        if not dsn.strip():
            raise ValueError('PostgreSQL URL is required')
        self.dsn = dsn
        # PracticeManager still needs an independent SQLite path for rehearsals.
        self.path = Path(practice_root) / 'snowfall.sqlite3'

    @contextmanager
    def connect(self):
        psycopg = _psycopg()
        # psycopg's context manager commits on successful exit, rolls back on
        # exceptions, then closes. No persistent cursors or transactions leak.
        with psycopg.connect(self.dsn, row_factory=compatible_row_factory,
                             connect_timeout=10, autocommit=False) as raw:
            yield ConnectionAdapter(raw)

    def initialize(self):
        """Require an explicitly migrated schema; never auto-create an empty game."""
        with self.connect() as connection:
            row = connection.execute(
                'SELECT version FROM snowfall_pg_meta WHERE singleton=1'
            ).fetchone()
            if row is None or row['version'] != DB_VERSION:
                raise RuntimeError('PostgreSQL migration not verified; run the offline v2.9.2 migrator')
            for table in ('players', 'season_state', 'score_ledger', 'social_arcade_runs',
                          'wire_submissions', 'wire_decisions'):
                present = connection.execute('SELECT to_regclass(?)', (table,)).fetchone()[0]
                if present is None:
                    raise RuntimeError(f'Incomplete PostgreSQL schema: missing {table}')

    def schema_version(self):
        with self.connect() as connection:
            return connection.execute('SELECT version FROM snowfall_pg_meta WHERE singleton=1').fetchone()[0]


def make_store(sqlite_path: Path, *, environment=None):
    """Production switches only when explicitly opted in; SQLite is default."""
    env = os.environ if environment is None else environment
    backend = env.get('SNOWFALL_DB_BACKEND', 'sqlite').strip().lower()
    if backend == 'sqlite':
        return Store(sqlite_path)
    if backend == 'postgres':
        dsn = env.get('SNOWFALL_DATABASE_URL', '').strip()
        if not dsn:
            raise ValueError('Set SNOWFALL_DATABASE_URL for an explicit PostgreSQL cutover')
        return PostgresStore(dsn, practice_root=sqlite_path.parent)
    raise ValueError('SNOWFALL_DB_BACKEND must be sqlite or postgres')

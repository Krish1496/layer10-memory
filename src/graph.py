"""
graph.py — Handles all database operations.
We use SQLite, which is a simple file-based database (no server needed).
The database stores: sources, entities, claims, evidence, and merge history.
"""

import sqlite3
import os
import uuid
from datetime import datetime

# Where the database file lives
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "outputs", "memory.db")


def get_conn():
    """Open a connection to the SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # lets us access columns by name
    return conn


def new_id():
    """Generate a short unique ID."""
    return str(uuid.uuid4())[:8]


def init_db():
    """Create all tables if they don't exist yet."""
    conn = get_conn()
    c = conn.cursor()

    # Raw source messages (the original emails)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id       TEXT PRIMARY KEY,
            author   TEXT,
            email    TEXT,
            subject  TEXT,
            body     TEXT,
            ts       TEXT
        )
    """)

    # Entities: people, projects, components, technologies
    c.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id           TEXT PRIMARY KEY,
            name         TEXT,
            type         TEXT,
            canonical_id TEXT,       -- points to the "winner" after dedup
            created_at   TEXT
        )
    """)

    # Aliases: other names for the same entity (for dedup)
    c.execute("""
        CREATE TABLE IF NOT EXISTS aliases (
            entity_id  TEXT,
            alias      TEXT,
            PRIMARY KEY (entity_id, alias)
        )
    """)

    # Claims: facts extracted from messages
    # e.g. "Alice LEADS Project Nexus"
    c.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id           TEXT PRIMARY KEY,
            subject_id   TEXT,         -- entity id
            predicate    TEXT,         -- e.g. LEADS, OWNS, USES, DECIDED_ON
            object_id    TEXT,         -- entity id (if object is an entity)
            object_value TEXT,         -- plain string (if object is not an entity)
            confidence   REAL,         -- 0.0 to 1.0
            is_current   INTEGER,      -- 1 = still true, 0 = no longer true
            valid_from   TEXT,
            valid_until  TEXT,
            created_at   TEXT
        )
    """)

    # Evidence: links a claim to the message that supports it
    c.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            id           TEXT PRIMARY KEY,
            claim_id     TEXT,
            source_id    TEXT,
            excerpt      TEXT,         -- the relevant sentence from the message
            offset_start INTEGER       -- character offset in the message body
        )
    """)

    # Merge log: audit trail so we can undo any dedup merge
    c.execute("""
        CREATE TABLE IF NOT EXISTS merge_log (
            id         TEXT PRIMARY KEY,
            from_id    TEXT,
            to_id      TEXT,
            merge_type TEXT,          -- "entity" or "claim"
            reason     TEXT,
            merged_at  TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("✓ Database ready.")


# ── Source helpers ────────────────────────────────────────────────────────────

def add_source(src):
    """Store a raw email message. Skips if already stored (idempotent)."""
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?)",
        (src["id"], src["author"], src["email"],
         src["subject"], src["body"], src["timestamp"])
    )
    conn.commit()
    conn.close()


# ── Entity helpers ────────────────────────────────────────────────────────────

def find_entity_by_name(name):
    """Return the entity id if an entity with this name already exists."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM entities WHERE lower(name) = lower(?)", (name,)
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def add_entity(name, entity_type):
    """
    Add an entity. If one with this name already exists, return its id.
    Returns the entity id.
    """
    existing = find_entity_by_name(name)
    if existing:
        return existing

    eid = new_id()
    conn = get_conn()
    conn.execute(
        "INSERT INTO entities VALUES (?,?,?,?,?)",
        (eid, name, entity_type, eid, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return eid


def add_alias(entity_id, alias):
    """Record that 'alias' is another name for entity_id."""
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO aliases VALUES (?,?)", (entity_id, alias)
    )
    conn.commit()
    conn.close()


def merge_entities(keep_id, drop_id, reason):
    """
    Merge drop_id into keep_id. All claims pointing to drop_id
    get updated to point to keep_id. We log the merge for auditing.
    """
    conn = get_conn()
    # Update claims that use drop_id as subject or object
    conn.execute(
        "UPDATE claims SET subject_id = ? WHERE subject_id = ?", (keep_id, drop_id)
    )
    conn.execute(
        "UPDATE claims SET object_id = ? WHERE object_id = ?", (keep_id, drop_id)
    )
    # Point drop entity to keep entity
    conn.execute(
        "UPDATE entities SET canonical_id = ? WHERE id = ?", (keep_id, drop_id)
    )
    # Log it
    conn.execute(
        "INSERT INTO merge_log VALUES (?,?,?,?,?,?)",
        (new_id(), drop_id, keep_id, "entity", reason, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


# ── Claim helpers ─────────────────────────────────────────────────────────────

def find_matching_claim(subject_id, predicate, object_id=None, object_value=None):
    """Return claim id if an identical claim already exists."""
    conn = get_conn()
    if object_id:
        row = conn.execute(
            """SELECT id FROM claims
               WHERE subject_id=? AND predicate=? AND object_id=?""",
            (subject_id, predicate, object_id)
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT id FROM claims
               WHERE subject_id=? AND predicate=? AND object_value=?""",
            (subject_id, predicate, object_value)
        ).fetchone()
    conn.close()
    return row["id"] if row else None


def add_claim(subject_id, predicate, object_id=None, object_value=None,
              confidence=0.8, is_current=True):
    """
    Add a claim. Returns (claim_id, is_new).
    If an identical claim already exists, return that id and is_new=False.
    """
    existing = find_matching_claim(subject_id, predicate, object_id, object_value)
    if existing:
        return existing, False

    cid = new_id()
    conn = get_conn()
    conn.execute(
        "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, subject_id, predicate, object_id, object_value,
         confidence, 1 if is_current else 0,
         datetime.now().isoformat(), None, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return cid, True


def mark_claim_historical(claim_id):
    """Mark a claim as no longer current (it was superseded)."""
    conn = get_conn()
    conn.execute(
        "UPDATE claims SET is_current=0, valid_until=? WHERE id=?",
        (datetime.now().isoformat(), claim_id)
    )
    conn.commit()
    conn.close()


# ── Evidence helpers ──────────────────────────────────────────────────────────

def add_evidence(claim_id, source_id, excerpt, offset=0):
    """Link a piece of evidence (message excerpt) to a claim."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO evidence VALUES (?,?,?,?,?)",
        (new_id(), claim_id, source_id, excerpt, offset)
    )
    conn.commit()
    conn.close()


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_all_canonical_entities():
    """Return all entities that haven't been merged away."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, type FROM entities WHERE id = canonical_id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_claims_for_entity(entity_id):
    """Return all claims where this entity is subject or object."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.id, c.subject_id, c.predicate, c.object_id,
                  c.object_value, c.confidence, c.is_current,
                  e1.name AS subject_name, e2.name AS object_name
           FROM claims c
           LEFT JOIN entities e1 ON c.subject_id = e1.id
           LEFT JOIN entities e2 ON c.object_id  = e2.id
           WHERE c.subject_id = ? OR c.object_id = ?""",
        (entity_id, entity_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_evidence_for_claim(claim_id):
    """Return all evidence items for a claim, with source metadata."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT ev.excerpt, ev.offset_start,
                  s.id AS source_id, s.author, s.ts, s.subject
           FROM evidence ev
           JOIN sources s ON ev.source_id = s.id
           WHERE ev.claim_id = ?""",
        (claim_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_merges():
    """Return the full merge audit log."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM merge_log").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_graph_for_viz():
    """Export everything as a dict, for the visualization HTML page."""
    conn = get_conn()

    entities = [dict(r) for r in conn.execute(
        "SELECT id, name, type FROM entities WHERE id = canonical_id"
    ).fetchall()]

    claims = [dict(r) for r in conn.execute(
        """SELECT c.id, c.subject_id, c.predicate, c.object_id,
                  c.object_value, c.confidence, c.is_current,
                  e1.name AS subject_name, e2.name AS object_name
           FROM claims c
           LEFT JOIN entities e1 ON c.subject_id = e1.id
           LEFT JOIN entities e2 ON c.object_id  = e2.id"""
    ).fetchall()]

    evidence = [dict(r) for r in conn.execute(
        """SELECT ev.claim_id, ev.excerpt, ev.offset_start,
                  s.id AS source_id, s.author, s.ts, s.subject
           FROM evidence ev JOIN sources s ON ev.source_id = s.id"""
    ).fetchall()]

    aliases = [dict(r) for r in conn.execute(
        "SELECT entity_id, alias FROM aliases"
    ).fetchall()]

    merges = [dict(r) for r in conn.execute(
        "SELECT from_id, to_id, merge_type, reason, merged_at FROM merge_log"
    ).fetchall()]

    conn.close()
    return {
        "entities": entities,
        "claims": claims,
        "evidence": evidence,
        "aliases": aliases,
        "merges": merges
    }

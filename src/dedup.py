"""
dedup.py — Deduplication and canonicalization.

Three kinds of dedup we do:
  1. Entity dedup: "A. Chen" and "Alice Chen" are the same person.
  2. Alias detection: "bob.m@nexus.com" is an alias for "Bob Martinez".
  3. Claim dedup: if the same fact appears in multiple messages,
     we keep ONE claim but attach ALL evidence to it.

We use simple string similarity so there are no extra libraries needed.
"""

import re
import sys
import os

# Add parent directory to path so we can import graph.py
sys.path.insert(0, os.path.dirname(__file__))
import graph


def normalize(name):
    """Lowercase, remove punctuation, collapse spaces."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def name_similarity(a, b):
    """
    Simple similarity score between two names.
    Returns a float 0.0–1.0.
    Strategy: check if one name is a prefix/suffix of the other,
    or if all words of the shorter name appear in the longer one.
    """
    a_norm = normalize(a)
    b_norm = normalize(b)

    if a_norm == b_norm:
        return 1.0

    # Check if the shorter is a prefix abbreviation of the longer
    # e.g. "A. Chen" vs "Alice Chen" — last names must match
    a_words = a_norm.split()
    b_words = b_norm.split()

    # If last words match, check if first words share a starting letter
    if a_words and b_words and a_words[-1] == b_words[-1]:
        a_first = a_words[0].rstrip(".")
        b_first = b_words[0].rstrip(".")
        if len(a_first) == 1 or len(b_first) == 1:
            if a_first[0] == b_first[0]:
                return 0.9   # e.g. "A. Chen" ≈ "Alice Chen"

    # Check if all words of the shorter name appear in the longer name
    shorter, longer = (a_words, b_words) if len(a_words) < len(b_words) else (b_words, a_words)
    if all(w in longer for w in shorter) and shorter:
        return 0.85

    # Check for email alias: "bob.m" vs "Bob Martinez"
    # If removing dots/numbers from one gives initials of the other
    a_initials = "".join(w[0] for w in a_words if w)
    b_initials = "".join(w[0] for w in b_words if w)
    if a_initials == b_initials and len(a_initials) >= 2:
        return 0.8

    return 0.0


def deduplicate_entities():
    """
    Find entities that refer to the same real-world thing and merge them.
    We group by entity type first (only merge Person with Person, etc.).
    The entity with the longer, more complete name is kept as canonical.
    """
    entities = graph.get_all_canonical_entities()

    # Group entities by type
    by_type = {}
    for e in entities:
        by_type.setdefault(e["type"], []).append(e)

    merge_count = 0

    for entity_type, group in by_type.items():
        # Compare every pair within the same type
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a = group[i]
                b = group[j]

                sim = name_similarity(a["name"], b["name"])
                if sim >= 0.8:
                    # Decide which to keep: prefer longer, more complete name
                    if len(a["name"]) >= len(b["name"]):
                        keep, drop = a, b
                    else:
                        keep, drop = b, a

                    reason = (f"Name similarity {sim:.2f}: "
                              f"'{drop['name']}' → '{keep['name']}'")
                    print(f"  Merging [{entity_type}] '{drop['name']}' → '{keep['name']}'")

                    # Register the old name as an alias
                    graph.add_alias(keep["id"], drop["name"])
                    # Merge in the database
                    graph.merge_entities(keep["id"], drop["id"], reason)
                    merge_count += 1

    print(f"  Entity dedup done. {merge_count} merges.")


def deduplicate_claims():
    """
    After entity dedup, find claims that are now identical and merge
    them by pointing all evidence to one representative claim.

    A 'duplicate claim' means: same subject_id + predicate + object_id
    (or object_value) appearing more than once.
    We keep the first one and re-link evidence from duplicates to it.
    """
    import sqlite3

    conn = graph.get_conn()

    # Find groups of claims with the same subject/predicate/object
    rows = conn.execute("""
        SELECT id, subject_id, predicate, object_id, object_value
        FROM claims
        ORDER BY created_at
    """).fetchall()

    # Build a dedup key → list of claim ids
    seen = {}   # key → first claim id
    duplicates = []   # (duplicate_id, canonical_id)

    for row in rows:
        key = (row["subject_id"], row["predicate"],
               row["object_id"], row["object_value"])
        if key in seen:
            duplicates.append((row["id"], seen[key]))
        else:
            seen[key] = row["id"]

    # Merge duplicate claims: re-point their evidence to the canonical claim
    for dup_id, canonical_id in duplicates:
        conn.execute(
            "UPDATE evidence SET claim_id = ? WHERE claim_id = ?",
            (canonical_id, dup_id)
        )
        conn.execute(
            "INSERT OR IGNORE INTO merge_log VALUES (?,?,?,?,?,?)",
            (graph.new_id(), dup_id, canonical_id, "claim",
             "Duplicate claim (same subject/predicate/object)",
             __import__("datetime").datetime.now().isoformat())
        )
        conn.execute("DELETE FROM claims WHERE id = ?", (dup_id,))

    conn.commit()
    conn.close()
    print(f"  Claim dedup done. {len(duplicates)} duplicates removed.")


def run_all_dedup():
    """Run the full deduplication pipeline."""
    print("\n── Deduplication ─────────────────────────────────")
    deduplicate_entities()
    deduplicate_claims()
    print("── Deduplication complete ─────────────────────────")

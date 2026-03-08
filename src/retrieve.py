"""
retrieve.py — Retrieval: answer questions using the memory graph.

Given a question, we:
  1. Find relevant entities by matching question keywords to entity names.
  2. Get all claims for those entities.
  3. For each claim, fetch its evidence (excerpts from source emails).
  4. Return a ranked list of (claim + evidence) items — a "context pack".

This is a simple keyword-based retrieval. In a production system you would
add embedding-based similarity search on top of this.
"""

import sys
import os
import re

sys.path.insert(0, os.path.dirname(__file__))
import graph


def tokenize(text):
    """Break text into lowercase words."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score_entity_for_query(entity_name, query_tokens):
    """
    How relevant is an entity to the question?
    Returns a float. Higher = more relevant.
    """
    entity_tokens = tokenize(entity_name)
    overlap = query_tokens & entity_tokens
    if not entity_tokens:
        return 0.0
    return len(overlap) / len(entity_tokens)


def retrieve(question, top_k_entities=3, top_k_claims=10):
    """
    Main retrieval function.

    Returns a context pack:
    {
      "question": "...",
      "matched_entities": [...],
      "results": [
        {
          "claim_id": "...",
          "subject": "...",
          "predicate": "...",
          "object": "...",
          "is_current": bool,
          "confidence": float,
          "evidence": [
            {"excerpt": "...", "author": "...", "timestamp": "...",
             "subject": "...", "source_id": "..."}
          ]
        },
        ...
      ]
    }
    """
    query_tokens = tokenize(question)

    # Step 1: find the most relevant entities
    all_entities = graph.get_all_canonical_entities()
    scored = []
    for e in all_entities:
        score = score_entity_for_query(e["name"], query_tokens)
        if score > 0:
            scored.append((score, e))

    # Sort by score, take top K
    scored.sort(key=lambda x: -x[0])
    top_entities = [e for _, e in scored[:top_k_entities]]

    if not top_entities:
        # Fallback: broad keyword match on claims
        return {
            "question": question,
            "matched_entities": [],
            "results": [],
            "note": "No matching entities found. Try different keywords."
        }

    # Step 2: collect all claims for matched entities
    seen_claim_ids = set()
    all_claims = []
    for entity in top_entities:
        claims = graph.get_claims_for_entity(entity["id"])
        for c in claims:
            if c["id"] not in seen_claim_ids:
                seen_claim_ids.add(c["id"])
                all_claims.append(c)

    # Step 3: rank claims by relevance to the question
    # Simple scoring: current claims score higher, high confidence scores higher
    def claim_score(claim):
        # Does the predicate match any query token?
        pred_score = len(query_tokens & tokenize(claim["predicate"])) * 0.3
        # Boost current claims
        current_boost = 0.4 if claim["is_current"] else 0.0
        # Confidence directly contributes
        conf = claim.get("confidence", 0.8)
        return pred_score + current_boost + conf

    all_claims.sort(key=claim_score, reverse=True)
    top_claims = all_claims[:top_k_claims]

    # Step 4: fetch evidence for each claim
    results = []
    for claim in top_claims:
        evidence = graph.get_evidence_for_claim(claim["id"])

        # Format the object nicely
        obj = claim.get("object_name") or claim.get("object_value") or "—"

        results.append({
            "claim_id":   claim["id"],
            "subject":    claim.get("subject_name") or claim["subject_id"],
            "predicate":  claim["predicate"],
            "object":     obj,
            "is_current": bool(claim["is_current"]),
            "confidence": claim.get("confidence", 0.8),
            "evidence":   evidence
        })

    return {
        "question":         question,
        "matched_entities": [e["name"] for e in top_entities],
        "results":          results
    }


def format_context_pack(pack):
    """Pretty-print a context pack to the terminal."""
    print(f"\n{'='*60}")
    print(f"Q: {pack['question']}")
    print(f"Matched entities: {', '.join(pack['matched_entities'])}")
    print(f"{'='*60}")

    if not pack["results"]:
        print("No results found.")
        return

    for i, r in enumerate(pack["results"], 1):
        status = "✓ current" if r["is_current"] else "✗ historical"
        print(f"\n[{i}] {r['subject']} —{r['predicate']}→ {r['object']}")
        print(f"    {status}  |  confidence: {r['confidence']:.0%}")

        for ev in r["evidence"]:
            print(f"    📧 {ev.get('author','?')} ({ev.get('ts','?')[:10]})")
            print(f"       \"{ev.get('excerpt','')[:120]}\"")
            print(f"       [source: {ev.get('source_id','?')} | subj: {ev.get('subject','?')}]")

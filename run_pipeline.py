"""
run_pipeline.py — Main script. Run this to build the memory graph end-to-end.

Usage:
    python run_pipeline.py            # demo mode (no API key needed)
    python run_pipeline.py --api      # use real Claude API (needs ANTHROPIC_API_KEY)

What it does:
    1. Loads the email corpus from data/corpus.json
    2. Extracts entities and claims from each email
    3. Deduplicates entities and claims
    4. Saves everything to outputs/memory.db (SQLite)
    5. Exports outputs/graph.json (for the visualization)
    6. Runs 3 example queries and saves outputs/context_packs.json
"""

import json
import os
import sys

# Make sure we can import from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import graph
import extract as extractor
import dedup
import retrieve

CORPUS_PATH  = os.path.join(os.path.dirname(__file__), "data", "corpus.json")
OUTPUTS_DIR  = os.path.join(os.path.dirname(__file__), "outputs")
GRAPH_JSON   = os.path.join(OUTPUTS_DIR, "graph.json")
PACKS_JSON   = os.path.join(OUTPUTS_DIR, "context_packs.json")

# Example queries we'll answer at the end
EXAMPLE_QUESTIONS = [
    "Who owns the Auth Module and what is its status?",
    "What database technology is Project Nexus using?",
    "What is Alice Chen responsible for?"
]


def load_corpus():
    with open(CORPUS_PATH, "r") as f:
        return json.load(f)


def ingest_message(message, use_api=False):
    """
    Process a single email message:
      - Store it as a source
      - Extract entities and claims
      - Save everything to the database
    """
    # Store the raw message
    graph.add_source(message)

    # Extract entities and claims
    result = extractor.extract_from_message(message, use_api=use_api)

    # ── Build a local map: extracted name → entity id ──────────────────
    name_to_id = {}

    for e in result.get("entities", []):
        name = e["name"].strip()
        etype = e["type"]
        eid = graph.add_entity(name, etype)
        name_to_id[name] = eid

    # ── Ingest claims ───────────────────────────────────────────────────
    for c in result.get("claims", []):
        subject_name = c["subject"].strip()
        object_name  = (c.get("object") or "").strip()
        predicate    = c["predicate"].strip().upper()
        confidence   = c.get("confidence", 0.8)
        is_current   = c.get("is_current", True)
        object_value = c.get("object_value", "").strip() if c.get("object_value") else None

        # Look up entity IDs (subject must exist; object may be a plain value)
        subject_id = name_to_id.get(subject_name)
        if not subject_id:
            # Try to find it in the database
            subject_id = graph.find_entity_by_name(subject_name)
        if not subject_id:
            continue   # can't link claim without a subject entity

        object_id = name_to_id.get(object_name) if object_name else None
        if not object_id and object_name:
            object_id = graph.find_entity_by_name(object_name)

        # If the claim says a previous fact is now false,
        # mark any existing matching claim as historical
        if not is_current:
            # Find if there's a current version of this claim to supersede
            existing = graph.find_matching_claim(
                subject_id, predicate,
                object_id=object_id, object_value=object_value
            )
            if existing:
                graph.mark_claim_historical(existing)

        # Add the claim
        claim_id, is_new = graph.add_claim(
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            object_value=object_value,
            confidence=confidence,
            is_current=is_current
        )

        # Build a short excerpt from the message body
        # (find the sentence most relevant to this claim)
        excerpt = find_excerpt(message["body"], subject_name, object_name or object_value or "")

        # Attach evidence
        graph.add_evidence(claim_id, message["id"], excerpt)


def find_excerpt(body, subject_name, object_str):
    """
    Find the sentence in the message body that best mentions
    the subject and/or object of a claim.
    Returns up to 200 chars.
    """
    sentences = [s.strip() for s in body.replace("\n", " ").split(".") if s.strip()]
    subject_lower = subject_name.lower()
    object_lower = object_str.lower() if object_str else ""

    best = None
    best_score = -1

    for sentence in sentences:
        s_lower = sentence.lower()
        score = (subject_lower in s_lower) + (object_lower in s_lower and object_lower != "")
        if score > best_score:
            best_score = score
            best = sentence

    if best:
        return best[:200]
    return body[:200]


def main():
    use_api = "--api" in sys.argv
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    print("Layer10 Memory Graph Pipeline")
    print("=" * 45)
    if use_api:
        print("Mode: REAL API (using GROQ_API_KEY — free Llama 3)")
    else:
        print("Mode: DEMO (pre-computed extractions, no API key needed)")
    print()

    # Step 1: Initialize DB
    graph.init_db()

    # Step 2: Load corpus
    corpus = load_corpus()
    print(f"\n── Ingesting {len(corpus)} messages ─────────────────")
    for msg in corpus:
        print(f"  Processing {msg['id']}: {msg['subject'][:50]}")
        ingest_message(msg, use_api=use_api)
    print("── Ingestion complete ─────────────────────────────")

    # Step 3: Deduplication
    dedup.run_all_dedup()

    # Step 4: Export graph JSON and update the visualization HTML
    graph_data = graph.export_graph_for_viz()
    with open(GRAPH_JSON, "w") as f:
        json.dump(graph_data, f, indent=2)
    print(f"\n✓ Graph exported → {GRAPH_JSON}")
    print(f"  {len(graph_data['entities'])} entities, "
          f"{len(graph_data['claims'])} claims, "
          f"{len(graph_data['evidence'])} evidence items, "
          f"{len(graph_data['merges'])} merges")

    # Also embed the fresh data directly into viz/index.html
    # so it works by just double-clicking the file (no server needed)
    viz_path = os.path.join(os.path.dirname(__file__), "viz", "index.html")
    if os.path.exists(viz_path):
        with open(viz_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Replace whatever is currently in EMBEDDED_DEMO_DATA with new data
        import re
        new_data = json.dumps(graph_data)
        # Use a function replacement to avoid re.sub misreading backslashes
        replacement = f"const EMBEDDED_DEMO_DATA = {new_data};"
        html = re.sub(
            r"const EMBEDDED_DEMO_DATA = .*?;",
            lambda m: replacement,
            html,
            flags=re.DOTALL
        )

        with open(viz_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✓ Visualization updated → {viz_path}")
    else:
        print(f"  (viz/index.html not found, skipping HTML update)")

    # Step 5: Run example retrieval queries
    print("\n── Example Retrieval Queries ──────────────────────")
    all_packs = []
    for question in EXAMPLE_QUESTIONS:
        pack = retrieve.retrieve(question)
        retrieve.format_context_pack(pack)
        all_packs.append(pack)

    with open(PACKS_JSON, "w") as f:
        json.dump(all_packs, f, indent=2)
    print(f"\n✓ Context packs saved → {PACKS_JSON}")
    print("\n✓ Done! Open viz/index.html in your browser to explore the graph.")


if __name__ == "__main__":
    main()

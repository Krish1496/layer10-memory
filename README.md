# Layer10 Take-Home — Grounded Long-Term Memory Graph

A pipeline that turns email messages into a queryable memory graph with entity extraction,
deduplication, evidence grounding, and an interactive visualization.

---

## Project Structure

```
layer10-memory/
├── data/
│   └── corpus.json          ← 15 sample email messages (Project Nexus team)
├── src/
│   ├── graph.py             ← SQLite database operations
│   ├── extract.py           ← Entity/claim extraction (demo + API mode)
│   ├── dedup.py             ← Entity and claim deduplication
│   └── retrieve.py          ← Keyword-based retrieval with grounding
├── outputs/
│   ├── memory.db            ← Generated SQLite graph (run pipeline to create)
│   ├── graph.json           ← Graph exported for the visualization
│   └── context_packs.json   ← 3 example retrieval results
├── viz/
│   └── index.html           ← Interactive graph explorer (self-contained)
├── run_pipeline.py          ← Main script — run this!
├── requirements.txt
├── writeup.md               ← Technical write-up
└── README.md
```

---

## Quick Start (Demo Mode — no API key needed)

```bash
# 1. Install dependencies (only needed for API mode, but good practice)
pip install anthropic

# 2. Run the pipeline
python run_pipeline.py

# 3. Open the visualization
# double-click viz/index.html in your file explorer
```

That's it. The pipeline will:
- Load 15 emails from `data/corpus.json`
- Extract entities and claims (from pre-computed demo data)
- Deduplicate entities (e.g., "A. Chen" → "Alice Chen")
- Save everything to `outputs/memory.db`
- Run 3 example queries and print grounded answers
- Export `outputs/graph.json` for the visualization

---

## API Mode (uses Google Gemini — FREE)

Get a free key (no credit card needed):
1. Go to **https://aistudio.google.com/app/apikey**
2. Sign in with your Google account
3. Click **"Create API Key"** and copy it

```powershell
# Windows PowerShell
$env:GEMINI_API_KEY="your-key-here"
python .\run_pipeline.py --api

# Mac/Linux Terminal
export GEMINI_API_KEY="your-key-here"
python run_pipeline.py --api
```

---

## Visualization

Open `viz/index.html` directly in any browser (no server needed — graph data is embedded).

**Features:**
- **Graph view** — nodes colored by type (Person, Project, Component, Technology, Infrastructure), edges labeled with predicates, dashed = historical claims
- **Click a node** → see all claims and evidence for that entity
- **Click a claim** → see the exact email excerpt(s) that support it
- **Filters** — show only current/historical claims, filter by entity type
- **Search tab** — keyword search across all claims
- **Merges tab** — audit log of all dedup merges

---

## Example Questions (from the pipeline output)

**"Who owns the Auth Module and what is its status?"**
→ Bob Martinez OWNS Auth Module (supported by msg_001)
→ Auth Module status: "Done — ready for launch" (supported by msg_015)
→ Historical: "P0 bug: memory leak" (supported by msg_007, superseded by msg_011)

**"What database technology is Project Nexus using?"**
→ Project Nexus USES PostgreSQL (current — after two reversals)
→ Historical: USES MySQL (superseded by msg_012)

**"What is Alice Chen responsible for?"**
→ Alice Chen LEADS Project Nexus
→ Alice Chen OWNS DataSync Core
→ Alice Chen DECIDED_ON React (for Frontend)
→ Alice Chen APPROVED AWS deployment

---

## How It Works

### 1. Extraction
Each email is sent to Claude (or loaded from demo data). The model returns structured JSON:
```json
{
  "entities": [{"name": "Alice Chen", "type": "Person"}],
  "claims":   [{"subject": "Alice Chen", "predicate": "LEADS",
                "object": "Project Nexus", "confidence": 0.95, "is_current": true}]
}
```

### 2. Entity Deduplication
The dedup module compares entity names within each type:
- "A. Chen" → "Alice Chen" (initial abbreviation match)
- Merges are logged for auditability and can be undone

### 3. Claim Versioning
When extraction says `is_current=false` for a claim, the existing matching claim gets
`valid_until` set and `is_current=0`. Both versions are kept in the DB.

### 4. Grounding
Every claim has at least one evidence row: `(source_id, excerpt, offset)`.
The retriever only returns claims with traceable evidence.

---

## Requirements

```
anthropic      # only needed for --api mode
```

Python 3.8+. No other dependencies — SQLite is built into Python.

---

## Reproducing from Scratch

```bash
# Remove generated files and re-run
rm -f outputs/memory.db outputs/graph.json outputs/context_packs.json
python run_pipeline.py
```

The corpus in `data/corpus.json` is the single source of truth.

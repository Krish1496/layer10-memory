"""
extract.py — Extracts entities and claims from email messages.

Uses Groq API — completely FREE, no credit card needed, very fast.
Model: llama-3.1-8b-instant (free, 14400 requests/day, no rate limit issues)

How to get a FREE Groq API key:
  1. Go to https://console.groq.com
  2. Sign up with Google or email (free, no credit card)
  3. Click "API Keys" in the left menu
  4. Click "Create API Key" and copy it

Then in PowerShell:
  $env:GROQ_API_KEY="gsk_your-key-here"
  python .\run_pipeline.py --api
"""

import json
import os
import urllib.request
import urllib.error

# ── Prompt ────────────────────────────────────────────────────────────────────

PROMPT = """You are an information-extraction assistant.
Given an email message, extract entities and claims.

Entity types allowed: Person, Project, Component, Technology, Infrastructure

Predicate types allowed: LEADS, OWNS, ASSIGNED_TO, USES, DECIDED_ON,
DEPLOYED_ON, HAS_STATUS, CHANGED_FROM, FIXED, APPROVED

Set is_current=false if a claim is described as historical or replaced.

Return ONLY valid JSON, no explanation, no markdown:
{
  "entities": [{"name": "...", "type": "..."}],
  "claims": [{"subject": "...", "predicate": "...", "object": "...",
              "confidence": 0.9, "is_current": true}]
}"""


def extract_with_api(message_body):
    """Call Groq API and return extracted entities + claims."""

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "\n\nGROQ_API_KEY not set!\n"
            "Get a FREE key (no credit card) at: https://console.groq.com\n"
            "Then in PowerShell run:\n"
            "  $env:GROQ_API_KEY=\"gsk_your-key-here\"\n"
            "  python .\\run_pipeline.py --api\n"
        )

    payload = json.dumps({
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user",   "content": message_body[:3000]}
        ],
        "temperature": 0.1,
        "max_tokens": 1000
    }).encode("utf-8")

    import time as _time, re as _re

    # Small fixed delay between every call so we stay under the
    # 6000 tokens/minute free tier limit (each email ~400 tokens)
    _time.sleep(2)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Retry up to 6 times on rate-limit errors
    result = None
    for attempt in range(6):
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers=headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            break  # success
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            if e.code == 429:
                # Read suggested wait time, e.g. "try again in 3.84s"
                match = _re.search(r"try again in ([\d.]+)s", error_body)
                wait = float(match.group(1)) + 2 if match else 15
                print(f"    Rate limit — waiting {wait:.0f}s (attempt {attempt+1}/6)...")
                _time.sleep(wait)
            else:
                raise RuntimeError(f"Groq API error {e.code}: {error_body}")

    if result is None:
        raise RuntimeError("Groq failed after 6 retries.")

    # Extract text from Groq's response
    raw = result["choices"][0]["message"]["content"].strip()

    # Strip accidental markdown fences (```json ... ```)
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else ""
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    # If the model returned nothing useful, return an empty result
    # instead of crashing (happens with very short/empty emails)
    if not raw or raw == "":
        print("    (model returned empty response, skipping this message)")
        return {"entities": [], "claims": []}

    # Find the JSON object inside the response in case there is extra text
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        print("    (no JSON found in response, skipping this message)")
        return {"entities": [], "claims": []}
    raw = raw[start:end]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("    (could not parse JSON response, skipping this message)")
        return {"entities": [], "claims": []}


# ── Demo extraction (no API key needed) ──────────────────────────────────────

DEMO_EXTRACTIONS = {
    "msg_001": {
        "entities": [
            {"name": "Diana Park",     "type": "Person"},
            {"name": "Alice Chen",     "type": "Person"},
            {"name": "Bob Martinez",   "type": "Person"},
            {"name": "Charlie Davis",  "type": "Person"},
            {"name": "Project Nexus",  "type": "Project"},
            {"name": "Auth Module",    "type": "Component"},
            {"name": "Frontend",       "type": "Component"}
        ],
        "claims": [
            {"subject": "Alice Chen",    "predicate": "LEADS",      "object": "Project Nexus", "confidence": 0.95, "is_current": True},
            {"subject": "Bob Martinez",  "predicate": "OWNS",       "object": "Auth Module",   "confidence": 0.95, "is_current": True},
            {"subject": "Charlie Davis", "predicate": "OWNS",       "object": "Frontend",      "confidence": 0.95, "is_current": True},
            {"subject": "Project Nexus", "predicate": "HAS_STATUS", "object": None, "object_value": "Launch target March 15", "confidence": 0.9, "is_current": True}
        ]
    },
    "msg_002": {
        "entities": [
            {"name": "Alice Chen",     "type": "Person"},
            {"name": "Project Nexus",  "type": "Project"},
            {"name": "DataSync Core",  "type": "Component"},
            {"name": "PostgreSQL",     "type": "Technology"}
        ],
        "claims": [
            {"subject": "Alice Chen",    "predicate": "OWNS", "object": "DataSync Core", "confidence": 0.95, "is_current": True},
            {"subject": "Project Nexus", "predicate": "USES", "object": "PostgreSQL",    "confidence": 0.9,  "is_current": True}
        ]
    },
    "msg_003": {
        "entities": [
            {"name": "Bob Martinez",  "type": "Person"},
            {"name": "Auth Module",   "type": "Component"},
            {"name": "Alice Chen",    "type": "Person"}
        ],
        "claims": [
            {"subject": "Auth Module", "predicate": "HAS_STATUS", "object": None, "object_value": "Design complete, implementation starting", "confidence": 0.9,  "is_current": True},
            {"subject": "Alice Chen",  "predicate": "APPROVED",   "object": "Auth Module", "confidence": 0.85, "is_current": True}
        ]
    },
    "msg_004": {
        "entities": [
            {"name": "Diana Park",    "type": "Person"},
            {"name": "MySQL",         "type": "Technology"},
            {"name": "PostgreSQL",    "type": "Technology"},
            {"name": "Project Nexus", "type": "Project"}
        ],
        "claims": [
            {"subject": "Project Nexus", "predicate": "USES",       "object": "PostgreSQL", "confidence": 0.9,  "is_current": False},
            {"subject": "Project Nexus", "predicate": "USES",       "object": "MySQL",      "confidence": 0.95, "is_current": True},
            {"subject": "Diana Park",    "predicate": "DECIDED_ON", "object": "MySQL",      "confidence": 0.95, "is_current": True}
        ]
    },
    "msg_005": {
        "entities": [
            {"name": "Charlie Davis", "type": "Person"},
            {"name": "A. Chen",       "type": "Person"},
            {"name": "Frontend",      "type": "Component"}
        ],
        "claims": []
    },
    "msg_006": {
        "entities": [
            {"name": "Alice Chen",    "type": "Person"},
            {"name": "Charlie Davis", "type": "Person"},
            {"name": "React",         "type": "Technology"},
            {"name": "Frontend",      "type": "Component"},
            {"name": "Project Nexus", "type": "Project"}
        ],
        "claims": [
            {"subject": "Frontend",   "predicate": "USES",       "object": "React", "confidence": 0.95, "is_current": True},
            {"subject": "Alice Chen", "predicate": "DECIDED_ON", "object": "React", "confidence": 0.9,  "is_current": True}
        ]
    },
    "msg_007": {
        "entities": [
            {"name": "Bob Martinez", "type": "Person"},
            {"name": "Auth Module",  "type": "Component"}
        ],
        "claims": [
            {"subject": "Auth Module",  "predicate": "HAS_STATUS",  "object": None, "object_value": "P0 bug: memory leak in session handler", "confidence": 0.95, "is_current": True},
            {"subject": "Bob Martinez", "predicate": "ASSIGNED_TO", "object": "Auth Module", "confidence": 0.9, "is_current": True}
        ]
    },
    "msg_008": {
        "entities": [
            {"name": "Alice Chen",    "type": "Person"},
            {"name": "Charlie Davis", "type": "Person"},
            {"name": "Bob Martinez",  "type": "Person"},
            {"name": "Auth Module",   "type": "Component"},
            {"name": "Frontend",      "type": "Component"}
        ],
        "claims": [
            {"subject": "Charlie Davis", "predicate": "ASSIGNED_TO", "object": "Auth Module", "confidence": 0.95, "is_current": True},
            {"subject": "Charlie Davis", "predicate": "ASSIGNED_TO", "object": "Frontend",    "confidence": 0.9,  "is_current": False}
        ]
    },
    "msg_009": {
        "entities": [
            {"name": "Diana Park",    "type": "Person"},
            {"name": "Project Nexus", "type": "Project"}
        ],
        "claims": [
            {"subject": "Project Nexus", "predicate": "HAS_STATUS", "object": None, "object_value": "Launch target March 15", "confidence": 0.9,  "is_current": False},
            {"subject": "Project Nexus", "predicate": "HAS_STATUS", "object": None, "object_value": "Launch target March 22", "confidence": 0.95, "is_current": True}
        ]
    },
    "msg_010": {
        "entities": [
            {"name": "Alice Chen",    "type": "Person"},
            {"name": "Eve Johnson",   "type": "Person"},
            {"name": "Charlie Davis", "type": "Person"},
            {"name": "Frontend",      "type": "Component"},
            {"name": "Auth Module",   "type": "Component"}
        ],
        "claims": [
            {"subject": "Charlie Davis", "predicate": "OWNS", "object": "Frontend", "confidence": 0.9,  "is_current": False},
            {"subject": "Eve Johnson",   "predicate": "OWNS", "object": "Frontend", "confidence": 0.95, "is_current": True}
        ]
    },
    "msg_011": {
        "entities": [
            {"name": "Bob Martinez",  "type": "Person"},
            {"name": "Charlie Davis", "type": "Person"},
            {"name": "Auth Module",   "type": "Component"}
        ],
        "claims": [
            {"subject": "Auth Module", "predicate": "HAS_STATUS", "object": None, "object_value": "P0 bug: memory leak in session handler",           "confidence": 0.9,  "is_current": False},
            {"subject": "Auth Module", "predicate": "FIXED",      "object": None, "object_value": "Memory leak fixed by Bob Martinez and Charlie Davis", "confidence": 0.95, "is_current": True}
        ]
    },
    "msg_012": {
        "entities": [
            {"name": "Alice Chen",    "type": "Person"},
            {"name": "Diana Park",    "type": "Person"},
            {"name": "PostgreSQL",    "type": "Technology"},
            {"name": "MySQL",         "type": "Technology"},
            {"name": "Project Nexus", "type": "Project"}
        ],
        "claims": [
            {"subject": "Project Nexus", "predicate": "USES",     "object": "MySQL",      "confidence": 0.9,  "is_current": False},
            {"subject": "Project Nexus", "predicate": "USES",     "object": "PostgreSQL", "confidence": 0.95, "is_current": True},
            {"subject": "Diana Park",    "predicate": "APPROVED", "object": "PostgreSQL", "confidence": 0.9,  "is_current": True}
        ]
    },
    "msg_013": {
        "entities": [
            {"name": "Bob Martinez",  "type": "Person"},
            {"name": "Alice Chen",    "type": "Person"},
            {"name": "Eve Johnson",   "type": "Person"},
            {"name": "Auth Module",   "type": "Component"},
            {"name": "DataSync Core", "type": "Component"},
            {"name": "Frontend",      "type": "Component"},
            {"name": "Project Nexus", "type": "Project"}
        ],
        "claims": [
            {"subject": "Auth Module",   "predicate": "HAS_STATUS", "object": None, "object_value": "80% complete", "confidence": 0.9, "is_current": True},
            {"subject": "DataSync Core", "predicate": "HAS_STATUS", "object": None, "object_value": "85% complete", "confidence": 0.9, "is_current": True},
            {"subject": "Frontend",      "predicate": "HAS_STATUS", "object": None, "object_value": "70% complete", "confidence": 0.9, "is_current": True}
        ]
    },
    "msg_014": {
        "entities": [
            {"name": "Diana Park",    "type": "Person"},
            {"name": "Alice Chen",    "type": "Person"},
            {"name": "Bob Martinez",  "type": "Person"},
            {"name": "AWS",           "type": "Infrastructure"},
            {"name": "Project Nexus", "type": "Project"}
        ],
        "claims": [
            {"subject": "Project Nexus", "predicate": "DEPLOYED_ON", "object": "AWS", "confidence": 0.95, "is_current": True},
            {"subject": "Alice Chen",    "predicate": "APPROVED",    "object": "AWS", "confidence": 0.9,  "is_current": True},
            {"subject": "Bob Martinez",  "predicate": "APPROVED",    "object": "AWS", "confidence": 0.9,  "is_current": True}
        ]
    },
    "msg_015": {
        "entities": [
            {"name": "Alice Chen",    "type": "Person"},
            {"name": "Bob Martinez",  "type": "Person"},
            {"name": "Eve Johnson",   "type": "Person"},
            {"name": "Diana Park",    "type": "Person"},
            {"name": "Auth Module",   "type": "Component"},
            {"name": "Frontend",      "type": "Component"},
            {"name": "DataSync Core", "type": "Component"},
            {"name": "Project Nexus", "type": "Project"}
        ],
        "claims": [
            {"subject": "Auth Module",   "predicate": "HAS_STATUS", "object": None, "object_value": "Done - ready for launch", "confidence": 0.95, "is_current": True},
            {"subject": "Frontend",      "predicate": "HAS_STATUS", "object": None, "object_value": "Done - ready for launch", "confidence": 0.95, "is_current": True},
            {"subject": "DataSync Core", "predicate": "HAS_STATUS", "object": None, "object_value": "Done - ready for launch", "confidence": 0.95, "is_current": True},
            {"subject": "Diana Park",    "predicate": "APPROVED",   "object": "Project Nexus", "confidence": 0.95, "is_current": True}
        ]
    }
}


def extract_from_message(message, use_api=False):
    """
    Extract entities and claims from a single message.
    use_api=True  → calls Groq (needs GROQ_API_KEY, free from console.groq.com)
    use_api=False → uses pre-computed demo results (no key needed)
    """
    if use_api:
        print(f"  Calling Groq for {message['id']}...")
        return extract_with_api(message["body"])
    else:
        result = DEMO_EXTRACTIONS.get(message["id"])
        if result is None:
            print(f"  WARNING: No demo extraction for {message['id']}, skipping.")
            return {"entities": [], "claims": []}
        return result

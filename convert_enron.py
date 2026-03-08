"""
convert_enron.py — Converts the Enron Kaggle CSV to corpus.json

The Kaggle CSV has two columns:
  file    → path like "maildir/allen-p/inbox/1."
  message → raw email text (headers + body)

Usage:
    python convert_enron.py                          # uses emails.csv in current folder
    python convert_enron.py --input my_file.csv      # custom input path
    python convert_enron.py --limit 100              # only take 100 emails (default: 50)
    python convert_enron.py --person allen-p         # only emails from one mailbox folder
    python convert_enron.py --output data/corpus.json

Output: corpus.json in the format the Layer10 pipeline expects.
"""

import csv
import json
import email
import re
import argparse
import os
from datetime import datetime


# ── Argument parsing ─────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--input",  default="emails.csv",        help="Path to the Kaggle CSV file")
parser.add_argument("--output", default="data/corpus.json",  help="Where to save corpus.json")
parser.add_argument("--limit",  type=int, default=50,        help="Max number of emails to include")
parser.add_argument("--person", default=None,                help="Only include emails from this mailbox (e.g. allen-p)")
parser.add_argument("--random", action="store_true",         help="Pick emails randomly instead of in order")
args = parser.parse_args()


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_address(addr):
    """
    Extract a clean email address from a messy string.
    e.g. 'Philip Allen <phillip.allen@enron.com>' → 'phillip.allen@enron.com'
    """
    if not addr:
        return ""
    # Look for <email> pattern first
    match = re.search(r"<([^>]+)>", addr)
    if match:
        return match.group(1).strip().lower()
    # Otherwise look for anything that looks like an email
    match = re.search(r"[\w.\-+]+@[\w.\-]+", addr)
    if match:
        return match.group(0).strip().lower()
    return addr.strip()


def extract_name(addr):
    """
    Extract a human-readable name from an email address field.
    'Philip Allen <phillip.allen@enron.com>' → 'Philip Allen'
    'phillip.allen@enron.com' → 'Phillip Allen'  (best-effort from the address)
    """
    if not addr:
        return "Unknown"
    # Try to get the display name before the <
    match = re.match(r"^([^<@,]+)<", addr)
    if match:
        name = match.group(1).strip().strip('"').strip("'")
        if name:
            return name
    # Fall back: use the local part of the email, title-cased
    email_part = clean_address(addr)
    local = email_part.split("@")[0] if "@" in email_part else email_part
    # Replace dots/underscores with spaces and title-case
    name = re.sub(r"[._\-]", " ", local).title()
    return name


def parse_date(date_str):
    """
    Parse email date strings into ISO format.
    Returns a string like '2001-05-14T09:00:00' or today if it fails.
    """
    if not date_str:
        return datetime.now().isoformat()

    # Try a few common email date formats
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",       # Mon, 14 May 2001 09:00:00 -0700
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
        "%d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M:%S",
    ]
    # Remove extra timezone junk like "(PDT)" at the end
    date_str = re.sub(r"\s*\([^)]*\)\s*$", "", date_str.strip())

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Return without timezone info for simplicity
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue

    return datetime.now().isoformat()


def clean_body(body):
    """
    Clean up email body text:
    - Remove quoted reply sections (lines starting with >)
    - Remove long lines of dashes/equals (email separators)
    - Collapse multiple blank lines
    - Strip leading/trailing whitespace
    """
    if not body:
        return ""

    lines = body.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip quoted lines
        if stripped.startswith(">"):
            continue
        # Skip separator lines
        if re.match(r"^[-=_*]{5,}$", stripped):
            continue
        # Skip "Original Message" headers
        if re.match(r"^-+\s*original message\s*-+$", stripped, re.IGNORECASE):
            break   # everything after this is quoted reply — stop
        cleaned.append(line)

    # Collapse 3+ blank lines into 2
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
    return result.strip()


def is_interesting(body, subject):
    """
    Very basic quality filter.
    Returns False for emails that are too short, automated, or empty.
    """
    if not body or len(body.strip()) < 30:
        return False
    # Skip automated/system emails
    boring_keywords = [
        "unsubscribe", "this is an automated", "do not reply",
        "delivery failure", "mail delivery", "out of office",
        "auto-reply", "vacation notice"
    ]
    combined = (body + " " + (subject or "")).lower()
    if any(kw in combined for kw in boring_keywords):
        return False
    return True


# ── Main conversion ───────────────────────────────────────────────────────────

def convert(input_path, output_path, limit, person_filter):
    print(f"Reading: {input_path}")
    print(f"Filter:  {'mailbox=' + person_filter if person_filter else 'all mailboxes'}")
    print(f"Limit:   {limit} emails")
    print()

    if not os.path.exists(input_path):
        print(f"ERROR: File not found: {input_path}")
        print("Make sure you downloaded emails.csv from Kaggle and it's in the current folder.")
        return

    results = []
    skipped = 0
    seen_subjects = set()  # simple dedup: skip emails with duplicate subjects

    # The Kaggle CSV can be large. We stream it row by row.
    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    if args.random:
        import random
        random.shuffle(all_rows)
        print(f"  Randomized order across {len(all_rows)} total emails.")

    with open(input_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)

        for row in all_rows:
            if len(results) >= limit:
                break

            file_path = row.get("file", "")
            raw_message = row.get("message", "")

            # Optional: filter to a specific person's mailbox folder
            if person_filter and person_filter.lower() not in file_path.lower():
                continue

            # Parse the raw email using Python's built-in email parser
            try:
                msg = email.message_from_string(raw_message)
            except Exception:
                skipped += 1
                continue

            # Extract fields
            from_field    = msg.get("From", "")
            subject_field = msg.get("Subject", "(no subject)").strip()
            date_field    = msg.get("Date", "")
            to_field      = msg.get("To", "")

            # Get body text
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        except Exception:
                            body = str(part.get_payload())
                        break
            else:
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                    else:
                        body = str(msg.get_payload())
                except Exception:
                    body = str(msg.get_payload())

            body = clean_body(body)

            # Quality filter
            if not is_interesting(body, subject_field):
                skipped += 1
                continue

            # Simple dedup: skip if we've seen this exact subject before
            subject_key = subject_field.lower().strip()
            if subject_key in seen_subjects:
                skipped += 1
                continue
            seen_subjects.add(subject_key)

            # Build the output record
            record = {
                "id":        f"msg_{len(results) + 1:03d}",
                "author":    extract_name(from_field),
                "email":     clean_address(from_field),
                "to":        to_field[:200] if to_field else "",
                "timestamp": parse_date(date_field),
                "subject":   subject_field[:200],
                "body":      body[:2000],   # cap at 2000 chars to keep things manageable
                "source_file": file_path
            }

            results.append(record)

            # Print progress every 10 emails
            if len(results) % 10 == 0:
                print(f"  Processed {len(results)} emails so far...")

    # Save output
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print()
    print(f"✓ Done!")
    print(f"  Kept:    {len(results)} emails")
    print(f"  Skipped: {skipped} (too short, automated, or duplicate subject)")
    print(f"  Saved:   {output_path}")
    print()
    print("Next step:")
    print("  python run_pipeline.py")


if __name__ == "__main__":
    convert(args.input, args.output, args.limit, args.person)
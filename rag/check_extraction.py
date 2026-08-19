"""
Extraction sanity check.

Dump the text of ONE paper to a .txt file so you can read it yourself and
decide whether the extraction is clean or garbled.

Run:
    python rag/check_extraction.py                  # uses the default paper
    python rag/check_extraction.py hu2018squeeze.pdf
"""

import sys
from pathlib import Path

import pdfplumber

RAG_DIR = Path(__file__).resolve().parent
REPO_ROOT = RAG_DIR.parent
PDF_FOLDER = REPO_ROOT / "data" / "papers"
OUT_DIR = REPO_ROOT / "data" / "extracted"

# sys.argv is the list of words you typed. [0] is this script's own name,
# so [1] is the first thing after it. Fall back to a default if nothing given.
PAPER = sys.argv[1] if len(sys.argv) > 1 else None
PAGES = 3   # how many pages to dump; bump this when you want a wider sample

pdf_path = PDF_FOLDER / PAPER
if not pdf_path.exists():
    raise SystemExit(f"Can't find {pdf_path}")

OUT_DIR.mkdir(parents=True, exist_ok=True)          # make the folder if it's new
out_path = OUT_DIR / f"{pdf_path.stem}.txt"         # .stem = filename minus ".pdf"

parts = []
with pdfplumber.open(pdf_path) as pdf:
    n = min(PAGES, len(pdf.pages))                  # don't ask for more pages than exist
    print(f"{PAPER}: {len(pdf.pages)} pages total, dumping first {n}")

    for i, page in enumerate(pdf.pages[:n], start=1):
        # extract_text() returns None on a page with no text layer (e.g. a scan),
        # so "or ''" keeps us from crashing when we join everything together.
        text = page.extract_text() or ""
        parts.append(f"\n{'=' * 70}\nPAGE {i}\n{'=' * 70}\n{text}")

full_text = "\n".join(parts)
out_path.write_text(full_text, encoding="utf-8")

# --- rough smell test -------------------------------------------------------
# These numbers are guesses, not science. They just nudge you to look closer.
lines = [ln for ln in full_text.splitlines() if ln.strip()]   # skip blank lines
avg_line = sum(len(ln) for ln in lines) / max(len(lines), 1)  # max(...,1) avoids /0

print(f"\ncharacters extracted : {len(full_text)}")
print(f"non-empty lines      : {len(lines)}")
print(f"average line length  : {avg_line:.0f}")

if len(full_text) < 500 * n:
    # a dense paper page is normally 3000+ characters
    print("\n[!] Very little text. This PDF may be scanned images, not real text.")
if avg_line > 130:
    # one column at ~10pt runs 70-90 chars; two columns merged is roughly double
    print("\n[!] Lines are unusually long. The two columns may have been merged.")

print(f"\nWrote: {out_path}")
print("Now open that file and read it. You are looking for:")
print("  - do sentences run on sensibly, or do they jump mid-thought?")
print("  - does a sentence from the left column get interrupted by the right?")
print("  - are the section headings (Abstract, 1. Introduction) in sensible places?")

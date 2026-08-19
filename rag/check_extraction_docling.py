"""
Same sanity check as check_extraction.py, but using Docling instead of pdfplumber.

Docling runs a layout model over the page: it works out what is a heading, a
paragraph, a table, a figure caption -- instead of dumping every character it
finds into one stream. That is why it should beat pdfplumber on our two
problems (missing spaces, figure axis labels spliced into sentences).

Install first (one package, MIT licensed):
    venv\\Scripts\\python.exe -m pip install docling

Run:
    venv\\Scripts\\python.exe rag\\check_extraction_docling.py
    venv\\Scripts\\python.exe rag\\check_extraction_docling.py hu2018squeeze.pdf

Heads up: the FIRST run downloads the layout models (a few hundred MB) and is
slow -- a minute or two per paper is normal. Later runs are much faster.
"""

import sys
from pathlib import Path

from docling.document_converter import DocumentConverter

RAG_DIR = Path(__file__).resolve().parent
REPO_ROOT = RAG_DIR.parent
PDF_FOLDER = REPO_ROOT / "data" / "papers"
OUT_DIR = REPO_ROOT / "data" / "extracted"

if len(sys.argv) < 2:
    PAPER = "he2016deep.pdf"        # same default as the pdfplumber script
else:
    PAPER = sys.argv[1]

pdf_path = PDF_FOLDER / PAPER
if not pdf_path.exists():
    raise SystemExit(f"Can't find {pdf_path}")

OUT_DIR.mkdir(parents=True, exist_ok=True)
# "_docling" suffix so this sits NEXT TO the pdfplumber .txt instead of
# overwriting it -- that is the whole point, we want to compare the two.
out_path = OUT_DIR / f"{pdf_path.stem}_docling.md"

print(f"Converting {PAPER} ... (slow on the first run, be patient)")

converter = DocumentConverter()
result = converter.convert(pdf_path)

# Markdown, not plain text: headings come out as "## 1. Introduction", so the
# document structure survives. That structure is what we will chunk on later.
markdown = result.document.export_to_markdown()
out_path.write_text(markdown, encoding="utf-8")

# --- same rough smell test as before, so the numbers are comparable ----------
lines = [ln for ln in markdown.splitlines() if ln.strip()]
avg_line = sum(len(ln) for ln in lines) / max(len(lines), 1)

print(f"\ncharacters extracted : {len(markdown)}")
print(f"non-empty lines      : {len(lines)}")
print(f"average line length  : {avg_line:.0f}")

print(f"\nWrote: {out_path}")
print("\nNow open BOTH files side by side and compare:")
print(f"  pdfplumber : data/extracted/{pdf_path.stem}.txt")
print(f"  docling    : data/extracted/{pdf_path.stem}_docling.md")
print("\nThings to check in the docling version:")
print("  - are the missing spaces fixed?  ('easethe' -> 'ease the')")
print("  - did the figure axis numbers stop appearing mid-sentence?")
print("  - are headings marked up as '#' / '##'?")
print("  - did anything get LOST that pdfplumber caught?")

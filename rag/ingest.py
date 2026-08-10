from pathlib import Path
import pdfplumber
RAG_DIR = Path(__file__).resolve().parent # getting rag folder 
REPO_ROOT =RAG_DIR.parent # find path of directory of ingest.py

PDF_FOLDER = REPO_ROOT/ "data" / "papers"

for pdf_path in PDF_FOLDER.glob("*.pdf"):
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Processing: {pdf_path.name}") 
        print(pdf.pages[0].extract_text()[:100]) # acces first page and print first 100 characters
        
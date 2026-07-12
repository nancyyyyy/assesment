"""
Ingests the policy/FAQ PDFs into a persistent Chroma collection.

Chunking strategy: split by section headers first (they're short, well-structured
policy docs), then fall back to a sliding window for any section that's still long.
Each chunk keeps its source filename + section title so we can cite it later.

Run: python ingest/ingest_docs.py
"""
import os
import re
import glob
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "docs")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")
COLLECTION_NAME = "policy_docs"

CHUNK_SIZE_CHARS = 800
CHUNK_OVERLAP_CHARS = 120


def extract_text(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _looks_like_header(line: str) -> bool:
    """Matches '1. Something' style headers AND short Title Case headers with
    no terminal punctuation (used by the FAQ doc, e.g. 'Order Tracking')."""
    line = line.strip()
    if not line or len(line) > 45:
        return False
    if re.match(r"^\d+\.\s+[A-Z]", line):
        return True
    if line[-1] in ".,;:":
        return False
    words = line.split()
    if 1 <= len(words) <= 6 and all(w[0].isupper() for w in words if w[0].isalpha()):
        return True
    return False


def split_into_sections(text: str, source: str):
    """Split on section headers. Handles both numbered headers ('1. Returns')
    and short Title Case headers with no numbering (used by the FAQ doc)."""
    lines = text.strip().split("\n")
    sections = []
    current_header = None
    current_lines = []

    for i, line in enumerate(lines):
        # skip the very first line (doc title) from being treated as a section break
        if i == 0:
            current_lines.append(line)
            continue
        if _looks_like_header(line):
            if current_lines:
                sections.append({
                    "header": current_header or lines[0].strip(),
                    "text": "\n".join(current_lines).strip(),
                })
            current_header = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "header": current_header or lines[0].strip(),
            "text": "\n".join(current_lines).strip(),
        })

    sections = [s for s in sections if s["text"]]
    if not sections:
        sections = [{"header": source, "text": text}]
    return sections


def chunk_section(section_text: str):
    """Sliding window fallback for any section longer than CHUNK_SIZE_CHARS."""
    if len(section_text) <= CHUNK_SIZE_CHARS:
        return [section_text]
    chunks = []
    start = 0
    while start < len(section_text):
        end = start + CHUNK_SIZE_CHARS
        chunks.append(section_text[start:end])
        start = end - CHUNK_OVERLAP_CHARS
    return chunks


def build_chunks():
    all_chunks = []
    pdf_paths = sorted(glob.glob(os.path.join(DOCS_DIR, "*.pdf")))
    if not pdf_paths:
        raise SystemExit(f"No PDFs found in {DOCS_DIR}")

    for pdf_path in pdf_paths:
        source_name = os.path.basename(pdf_path)
        text = extract_text(pdf_path)
        # first line of the doc is usually the title, e.g. "Northwind Gadgets — Warranty Policy"
        title = text.strip().split("\n")[0].strip()
        sections = split_into_sections(text, source_name)

        for sec_idx, sec in enumerate(sections):
            sub_chunks = chunk_section(sec["text"])
            for sub_idx, chunk_text in enumerate(sub_chunks):
                all_chunks.append({
                    "id": f"{source_name}::sec{sec_idx}::part{sub_idx}",
                    "text": chunk_text.strip(),
                    "metadata": {
                        "source": source_name,
                        "doc_title": title,
                        "section": sec["header"][:80],
                    },
                })
    return all_chunks


def main():
    import chromadb
    from chromadb.utils import embedding_functions

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Set OPENAI_API_KEY in your environment or .env file")

    chunks = build_chunks()
    print(f"Built {len(chunks)} chunks from {len(glob.glob(os.path.join(DOCS_DIR, '*.pdf')))} PDFs")

    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Wipe and recreate so re-running ingestion is idempotent during development
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=api_key, model_name="text-embedding-3-small"
    )
    collection = client.create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)

    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )

    print(f"Ingested {len(chunks)} chunks into Chroma collection '{COLLECTION_NAME}' at {CHROMA_DIR}")
    for c in chunks[:3]:
        print(" -", c["id"], "|", c["metadata"]["section"])


if __name__ == "__main__":
    main()

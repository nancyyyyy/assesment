"""
RAG retrieval over the policy docs. Returns chunks + a synthesized answer
with inline citations back to (source file, section).
"""
import os
import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")
COLLECTION_NAME = "policy_docs"
TOP_K = 4
# Chroma cosine distance above this = treat as "not relevant enough" -> fallback
RELEVANCE_DISTANCE_THRESHOLD = 0.45

_client = None
_collection = None
_openai = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        api_key = os.environ["OPENAI_API_KEY"]
        embed_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key, model_name="text-embedding-3-small"
        )
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_collection(COLLECTION_NAME, embedding_function=embed_fn)
    return _collection


def _get_openai():
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai


def retrieve(question: str, top_k: int = TOP_K):
    collection = _get_collection()
    results = collection.query(query_texts=[question], n_results=top_k)

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({"text": doc, "source": meta["source"], "section": meta["section"], "distance": dist})
    return hits


def answer_from_docs(question: str) -> dict:
    """Returns {answer, citations, used_fallback, raw_hits}."""
    hits = retrieve(question)

    if not hits or hits[0]["distance"] > RELEVANCE_DISTANCE_THRESHOLD:
        return {
            "answer": "I don't have that information in the available documents.",
            "citations": [],
            "used_fallback": True,
            "raw_hits": hits,
        }

    context_blocks = []
    for i, h in enumerate(hits):
        context_blocks.append(f"[{i+1}] Source: {h['source']} | Section: {h['section']}\n{h['text']}")
    context = "\n\n".join(context_blocks)

    system_prompt = (
        "You answer questions using ONLY the provided document excerpts. "
        "Every factual claim must be followed by a citation marker like [1] or [2] "
        "referencing the excerpt it came from. "
        "If the excerpts do not contain the answer, say "
        "\"I don't have that information in the available documents.\" and nothing else. "
        "Do not use outside knowledge. Do not invent policy details."
    )
    user_prompt = f"Document excerpts:\n{context}\n\nQuestion: {question}"

    client = _get_openai()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    answer_text = resp.choices[0].message.content

    used_fallback = "don't have that information" in answer_text.lower()
    citations = [] if used_fallback else [
        {"marker": i + 1, "source": h["source"], "section": h["section"]}
        for i, h in enumerate(hits)
    ]

    return {
        "answer": answer_text,
        "citations": citations,
        "used_fallback": used_fallback,
        "raw_hits": hits,
    }

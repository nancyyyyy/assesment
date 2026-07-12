"""
Proves the RAG path works end to end before any FastAPI/UI is built.
Run: python scripts/test_rag.py
"""
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from app.rag import answer_from_docs  # noqa: E402

TEST_QUESTIONS = [
    "What is the return window for eligible products?",
    "How many paid sick leave days do employees get?",
    "Can I combine a promo code with a bulk discount?",
    "What's the capital of France?",  # out-of-scope, should fallback
]

if __name__ == "__main__":
    for q in TEST_QUESTIONS:
        print("=" * 70)
        print("Q:", q)
        result = answer_from_docs(q)
        print("A:", result["answer"])
        print("Citations:", result["citations"])
        print("Fallback used:", result["used_fallback"])

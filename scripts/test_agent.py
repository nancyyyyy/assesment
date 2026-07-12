"""
Proves the agent correctly routes to search_docs / query_orders / both,
before any FastAPI/UI is built.
Run: python scripts/test_agent.py
"""
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from app.agent import answer  # noqa: E402

TEST_QUESTIONS = [
    ("Document-only", "What is the return window for eligible products?"),
    ("SQL-only", "How many orders are currently pending?"),
    ("Mixed", "Our policy allows 30-day returns. If a customer requested a return today (15 June 2026) for order ORD-1002, would it still qualify?"),
    ("Out-of-scope", "What's the weather like today?"),
]

if __name__ == "__main__":
    for label, q in TEST_QUESTIONS:
        print("=" * 70)
        print(f"[{label}] Q: {q}")
        result = answer(q)
        print("A:", result["answer"])
        print("Tools used:", result["tools_used"])
        if result["citations"]:
            print("Citations:", result["citations"])
        if result["sql_queries"]:
            print("SQL:", result["sql_queries"])

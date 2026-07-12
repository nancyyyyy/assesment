"""
Proves the text-to-SQL path works end to end before any FastAPI/UI is built.
Run: python scripts/test_sql.py
"""
import sys
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from app.sql_tool import answer_from_sql  # noqa: E402

TEST_QUESTIONS = [
    "How many orders are currently pending?",
    "What was total revenue last month?",
    "List the 5 most recent delivered orders.",
    "What is the CEO's salary?",  # out-of-scope / hallucination trap
]

if __name__ == "__main__":
    for q in TEST_QUESTIONS:
        print("=" * 70)
        print("Q:", q)
        result = answer_from_sql(q)
        print("SQL:", result["sql"])
        print("A:", result["answer"])
        print("Fallback used:", result["used_fallback"])

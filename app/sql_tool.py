"""
Text-to-SQL over the orders table. The LLM is given the exact schema (not the
data) and must output ONLY a SELECT statement. Guardrails:
  - reject anything that isn't a single SELECT statement
  - reject any column name not present in the real schema (catches hallucinated columns)
  - reject write/DDL keywords even if they slip past the SELECT check
  - query runs against a read-only sqlite connection
"""
import os
import re
import sqlite3
from openai import OpenAI

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "orders.db")

SCHEMA = {
    "orders": ["order_id", "customer", "product", "amount", "status", "order_date"]
}

# The "current date" fiction the assessment specifies, so relative questions
# ("last month", "this week") resolve against a fixed anchor instead of the
# real system clock.
ANCHOR_DATE = "2026-06-15"

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|PRAGMA|REPLACE|TRUNCATE)\b",
    re.IGNORECASE,
)

_openai = None


def _get_openai():
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai


def generate_sql(question: str) -> str:
    schema_desc = "Table: orders(" + ", ".join(SCHEMA["orders"]) + ")\n" \
        "  order_id TEXT, customer TEXT, product TEXT, amount REAL, " \
        "status TEXT (one of: pending, processing, shipped, delivered, cancelled, returned), " \
        "order_date TEXT (ISO format YYYY-MM-DD)"

    system_prompt = (
        "You translate natural language questions into a single SQLite SELECT statement.\n"
        f"{schema_desc}\n"
        f"Treat '{ANCHOR_DATE}' as today's date for any relative date question "
        "(e.g. 'last month', 'this week').\n"
        "Rules:\n"
        "- Output ONLY the raw SQL, no markdown fences, no explanation.\n"
        "- Only use columns that exist in the schema above. Never invent columns.\n"
        "- Only generate SELECT statements. Never write/modify data.\n"
        "- If the question cannot be answered from this schema, output exactly: NOT_APPLICABLE"
    )

    client = _get_openai()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0,
    )
    sql = resp.choices[0].message.content.strip()
    sql = re.sub(r"^```sql|^```|```$", "", sql, flags=re.MULTILINE).strip()
    return sql


def validate_sql(sql: str) -> tuple[bool, str]:
    if sql == "NOT_APPLICABLE":
        return False, "not_applicable"

    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        return False, "not_a_select_statement"

    if FORBIDDEN_KEYWORDS.search(sql):
        return False, "forbidden_keyword"

    if ";" in sql.strip().rstrip(";"):
        return False, "multiple_statements"

    # crude but effective column-hallucination guard: every bare identifier-looking
    # token that isn't a known column/keyword/table must not silently pass through
    sql_no_strings = re.sub(r"'[^']*'", "''", sql)
    used_columns = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", sql_no_strings))
    known_ok = set(SCHEMA["orders"]) | {
        "orders", "SELECT", "FROM", "WHERE", "AND", "OR", "COUNT", "SUM", "AVG",
        "MIN", "MAX", "GROUP", "BY", "ORDER", "LIMIT", "AS", "DESC", "ASC",
        "NOT", "IN", "LIKE", "BETWEEN", "IS", "NULL", "DISTINCT", "STRFTIME",
        "ROUND", "CAST", "REAL", "TEXT",
    }
    suspicious = {c for c in used_columns if c.isidentifier()} - known_ok - {
        c.upper() for c in known_ok
    }
    # allow anything that's clearly a string/number literal context; this is a
    # best-effort guard, not a full SQL parser
    suspicious = {c for c in suspicious if not c.isdigit()}
    if suspicious:
        return False, f"unknown_identifier:{','.join(sorted(suspicious))}"

    return True, "ok"


def run_sql(sql: str):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cur = conn.execute(sql)
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()
    return columns, rows


def answer_from_sql(question: str) -> dict:
    sql = generate_sql(question)
    ok, reason = validate_sql(sql)

    if not ok:
        return {
            "answer": "I don't have that information.",
            "sql": sql,
            "used_fallback": True,
            "reason": reason,
        }

    try:
        columns, rows = run_sql(sql)
    except sqlite3.Error as e:
        return {
            "answer": "I don't have that information.",
            "sql": sql,
            "used_fallback": True,
            "reason": f"sql_error:{e}",
        }

    return {
        "answer": format_result(columns, rows),
        "sql": sql,
        "used_fallback": False,
        "columns": columns,
        "rows": rows,
    }


def format_result(columns, rows) -> str:
    if not rows:
        return "No matching orders found."
    if len(rows) == 1 and len(columns) == 1:
        return f"{columns[0]}: {rows[0][0]}"
    preview = rows[:10]
    lines = [", ".join(columns)]
    lines += [", ".join(str(v) for v in r) for r in preview]
    suffix = f"\n... ({len(rows)} rows total)" if len(rows) > 10 else ""
    return "\n".join(lines) + suffix

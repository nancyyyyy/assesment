"""
The agent/router. This is the core of the assignment: a single LLM loop with
two tools (search_docs, query_orders). The model decides per question which
tool(s) to call, and can call both in sequence for mixed questions (e.g. it
can query an order's status first, then reason against a retrieved policy
chunk using that result).

This intentionally does NOT hand-code routing rules (no keyword matching on
"revenue" -> SQL, "policy" -> docs). The LLM sees both tool descriptions and
chooses, which is what makes this "agentic" rather than a fixed pipeline.
"""
import os
import json
from openai import OpenAI

from app.rag import retrieve, RELEVANCE_DISTANCE_THRESHOLD
from app.sql_tool import generate_sql, validate_sql, run_sql, format_result

MODEL = "gpt-4o-mini"
MAX_TOOL_ITERATIONS = 4

_openai = None


def _get_openai():
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the company's policy and FAQ documents (HR leave policy, "
                "product FAQ, returns/refunds policy, warranty policy, pricing/"
                "discounts policy). Use this for questions about rules, policies, "
                "procedures, or general company information. Returns the most "
                "relevant excerpts with their source document and section."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_orders",
            "description": (
                "Query the structured orders database (order_id, customer, product, "
                "amount, status, order_date). Use this for questions about specific "
                "orders, revenue, order counts, order statuses, or any question "
                "requiring aggregation/filtering over order data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The data question in natural language",
                    }
                },
                "required": ["question"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are a support assistant for Northwind Gadgets. You have two tools: "
    "search_docs (for policy/FAQ questions) and query_orders (for order data "
    "questions). Use whichever tool(s) the question needs — call both if the "
    "question spans both a policy and specific order data (e.g. checking if an "
    "order qualifies under a policy rule). \n\n"
    "IMPORTANT — how to phrase query_orders calls: query_orders can only "
    "translate plain data-fetch questions into SQL (e.g. 'what is the status "
    "and order_date for order ORD-1002'). It cannot judge eligibility, apply "
    "policy rules, or answer subjective questions. If a question requires both "
    "a policy judgment and order data, call query_orders with ONLY the factual "
    "lookup part (e.g. order date/status/amount), then apply the policy "
    "reasoning yourself using what search_docs returned.\n\n"
    "Rules:\n"
    "- Only answer using information returned by the tools. Never use outside "
    "knowledge and never invent policy details, numbers, or SQL columns.\n"
    "- When you use search_docs results, cite the source like [source: file, "
    "section].\n"
    "- When you use query_orders results, mention the SQL query that was run.\n"
    "- If neither tool returns relevant information for the question, respond "
    "exactly: \"I don't have that information.\"\n"
    "- Do not call a tool for questions clearly unrelated to company policies or "
    "order data (e.g. general knowledge questions) — just give the fallback."
)


def _execute_tool(name: str, args: dict) -> dict:
    """Runs the actual tool and returns a JSON-serializable result plus
    metadata we want to surface to the UI later (citations / SQL)."""
    if name == "search_docs":
        hits = retrieve(args["query"])
        if not hits or hits[0]["distance"] > RELEVANCE_DISTANCE_THRESHOLD:
            return {
                "result_for_model": {"found": False, "excerpts": []},
                "ui_meta": {"type": "docs", "citations": []},
            }
        excerpts = [
            {"source": h["source"], "section": h["section"], "text": h["text"]}
            for h in hits
        ]
        return {
            "result_for_model": {"found": True, "excerpts": excerpts},
            "ui_meta": {
                "type": "docs",
                "citations": [{"source": e["source"], "section": e["section"]} for e in excerpts],
            },
        }

    if name == "query_orders":
        sql = generate_sql(args["question"])
        ok, reason = validate_sql(sql)
        if not ok:
            return {
                "result_for_model": {"found": False, "reason": reason},
                "ui_meta": {"type": "sql", "sql": sql, "ok": False},
            }
        try:
            columns, rows = run_sql(sql)
        except Exception as e:
            return {
                "result_for_model": {"found": False, "reason": f"sql_error:{e}"},
                "ui_meta": {"type": "sql", "sql": sql, "ok": False},
            }
        return {
            "result_for_model": {
                "found": True,
                "sql": sql,
                "formatted_result": format_result(columns, rows),
                "row_count": len(rows),
            },
            "ui_meta": {"type": "sql", "sql": sql, "ok": True, "row_count": len(rows)},
        }

    raise ValueError(f"Unknown tool: {name}")


def answer(question: str, history: list[dict] | None = None) -> dict:
    """
    Runs the agent loop. Returns:
      {
        "answer": str,
        "tools_used": ["search_docs", "query_orders", ...],
        "citations": [...],   # deduped, from any search_docs calls
        "sql_queries": [...], # from any query_orders calls
      }
    """
    client = _get_openai()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    tools_used = []
    citations = []
    sql_queries = []

    for _ in range(MAX_TOOL_ITERATIONS):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto", temperature=0,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return {
                "answer": msg.content,
                "tools_used": tools_used,
                "citations": citations,
                "sql_queries": sql_queries,
            }

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            tools_used.append(name)

            exec_result = _execute_tool(name, args)

            if exec_result["ui_meta"]["type"] == "docs":
                citations.extend(exec_result["ui_meta"]["citations"])
            elif exec_result["ui_meta"]["type"] == "sql":
                sql_queries.append(exec_result["ui_meta"])

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(exec_result["result_for_model"]),
            })

    # safety valve: if we somehow loop MAX_TOOL_ITERATIONS times without a final
    # answer, force one more call with tool_choice disabled
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=0)
    return {
        "answer": resp.choices[0].message.content,
        "tools_used": tools_used,
        "citations": citations,
        "sql_queries": sql_queries,
    }


def stream_answer(question: str, history: list[dict] | None = None):
    """
    Generator version for the FastAPI SSE endpoint. Yields dicts:
      {"type": "token", "text": "..."}                    -- live answer tokens
      {"type": "tool_call", "name": "search_docs", ...}     -- fired when a tool starts
      {"type": "done", "tools_used": [...], "citations": [...], "sql_queries": [...]}

    Streams every round from the API. A round where the model emits tool_call
    deltas is buffered silently (arguments aren't usable until fully assembled
    anyway); a round with no tool calls is the final answer and its tokens are
    forwarded live as they arrive.
    """
    client = _get_openai()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    tools_used = []
    citations = []
    sql_queries = []

    for _ in range(MAX_TOOL_ITERATIONS):
        stream = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto",
            temperature=0, stream=True,
        )

        collected_content = ""
        collected_tool_calls: dict[int, dict] = {}
        started_streaming_content = False

        for chunk in stream:
            delta = chunk.choices[0].delta

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in collected_tool_calls:
                        collected_tool_calls[idx] = {"id": None, "name": "", "arguments": ""}
                    if tc_delta.id:
                        collected_tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        collected_tool_calls[idx]["name"] += tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        collected_tool_calls[idx]["arguments"] += tc_delta.function.arguments

            if delta.content:
                collected_content += delta.content
                # only forward live if no tool call has appeared in this round so far
                if not collected_tool_calls:
                    started_streaming_content = True
                    yield {"type": "token", "text": delta.content}

        if collected_tool_calls:
            messages.append({
                "role": "assistant",
                "content": collected_content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in collected_tool_calls.values()
                ],
            })

            for tc in collected_tool_calls.values():
                name = tc["name"]
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                tools_used.append(name)
                yield {"type": "tool_call", "name": name, "args": args}

                exec_result = _execute_tool(name, args)

                if exec_result["ui_meta"]["type"] == "docs":
                    citations.extend(exec_result["ui_meta"]["citations"])
                elif exec_result["ui_meta"]["type"] == "sql":
                    sql_queries.append(exec_result["ui_meta"])

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(exec_result["result_for_model"]),
                })
            continue  # next round: get the final streamed answer

        # no tool calls this round -> tokens were already streamed live above
        if started_streaming_content or collected_content:
            yield {
                "type": "done",
                "tools_used": tools_used,
                "citations": citations,
                "sql_queries": sql_queries,
            }
            return

    # safety valve
    resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=0)
    yield {"type": "token", "text": resp.choices[0].message.content}
    yield {
        "type": "done",
        "tools_used": tools_used,
        "citations": citations,
        "sql_queries": sql_queries,
    }

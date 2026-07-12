"use client";

import { useState, useRef, useEffect } from "react";
import { ToolBadge, Citation, SqlBlock } from "./ToolBadge";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type CitationData = { source: string; section: string };
type SqlQuery = { sql: string; ok: boolean };

type Message = {
  role: "user" | "assistant";
  text: string;
  toolsUsed: string[];
  citations: CitationData[];
  sqlQueries: SqlQuery[];
  isStreaming?: boolean;
};

const SUGGESTIONS = [
  "What is the return window for eligible products?",
  "How many orders are currently pending?",
  "Our policy allows 30-day returns — does order ORD-1002 still qualify today?",
];

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(question: string) {
    if (!question.trim() || isSending) return;
    setIsSending(true);
    setInput("");

    setMessages((prev) => [
      ...prev,
      { role: "user", text: question, toolsUsed: [], citations: [], sqlQueries: [] },
      { role: "assistant", text: "", toolsUsed: [], citations: [], sqlQueries: [], isStreaming: true },
    ]);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question }),
      });

      if (!res.body) throw new Error("No response body");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          const jsonStr = line.slice(5).trim();
          if (!jsonStr) continue;

          let event: any;
          try {
            event = JSON.parse(jsonStr);
          } catch {
            continue;
          }

          setMessages((prev) => {
            const next = [...prev];
            const last = { ...next[next.length - 1] };

            if (event.type === "token") {
              last.text = last.text + event.text;
            } else if (event.type === "tool_call") {
              last.toolsUsed = last.toolsUsed.includes(event.name)
                ? last.toolsUsed
                : [...last.toolsUsed, event.name];
            } else if (event.type === "done") {
              last.toolsUsed = event.tools_used || last.toolsUsed;
              last.citations = dedupeCitations(event.citations || []);
              last.sqlQueries = event.sql_queries || [];
              last.isStreaming = false;
            } else if (event.type === "error") {
              last.text = "Something went wrong on the server. Please try again.";
              last.isStreaming = false;
            }

            next[next.length - 1] = last;
            return next;
          });
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        last.text = "Couldn't reach the server. Is the backend running?";
        last.isStreaming = false;
        return next;
      });
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 20, marginBottom: 20 }}>
        {messages.length === 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                style={{
                  textAlign: "left",
                  background: "var(--paper-raised)",
                  border: "1px solid var(--rule)",
                  borderRadius: 4,
                  padding: "12px 14px",
                  fontFamily: "var(--font-body)",
                  fontSize: 14,
                  color: "var(--ink)",
                  cursor: "pointer",
                }}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--ink-soft)",
              }}
            >
              {m.role === "user" ? "You" : "Support Desk"}
            </div>
            <div
              style={{
                background: m.role === "user" ? "transparent" : "var(--paper-raised)",
                border: m.role === "user" ? "none" : "1px solid var(--rule)",
                borderRadius: 4,
                padding: m.role === "user" ? "0" : "14px 16px",
                fontSize: 15,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
              }}
            >
              {m.text || (m.isStreaming ? <Pulse /> : "")}
            </div>

            {m.toolsUsed.length > 0 && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 2 }}>
                {m.toolsUsed.map((t, idx) => (
                  <ToolBadge key={idx} tool={t as any} />
                ))}
              </div>
            )}

            {m.citations.map((c, idx) => (
              <Citation key={idx} source={c.source} section={c.section} />
            ))}

            {m.sqlQueries.map((q, idx) => (
              <SqlBlock key={idx} sql={q.sql} />
            ))}
          </div>
        ))}
        <div ref={scrollRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        style={{
          display: "flex",
          gap: 8,
          borderTop: "1px solid var(--rule)",
          paddingTop: 16,
          position: "sticky",
          bottom: 0,
          background: "var(--paper)",
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          disabled={isSending}
          style={{
            flex: 1,
            fontFamily: "var(--font-body)",
            fontSize: 15,
            padding: "12px 14px",
            border: "1px solid var(--rule)",
            borderRadius: 4,
            background: "var(--paper-raised)",
            color: "var(--ink)",
          }}
        />
        <button
          type="submit"
          disabled={isSending || !input.trim()}
          style={{
            fontFamily: "var(--font-body)",
            fontWeight: 600,
            fontSize: 14,
            padding: "12px 20px",
            border: "none",
            borderRadius: 4,
            background: "var(--teal)",
            color: "var(--paper-raised)",
            cursor: isSending ? "default" : "pointer",
            opacity: isSending || !input.trim() ? 0.6 : 1,
          }}
        >
          Send
        </button>
      </form>
    </div>
  );
}

function dedupeCitations(citations: CitationData[]): CitationData[] {
  const seen = new Set<string>();
  const out: CitationData[] = [];
  for (const c of citations) {
    const key = `${c.source}::${c.section}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push(c);
    }
  }
  return out;
}

function Pulse() {
  return (
    <span style={{ display: "inline-flex", gap: 4 }}>
      <Dot delay={0} />
      <Dot delay={150} />
      <Dot delay={300} />
    </span>
  );
}

function Dot({ delay }: { delay: number }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: "50%",
        background: "var(--ink-soft)",
        display: "inline-block",
        animation: "pulse 1s infinite",
        animationDelay: `${delay}ms`,
      }}
    />
  );
}

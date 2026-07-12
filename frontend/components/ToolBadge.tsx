"use client";

type ToolBadgeProps = {
  tool: "search_docs" | "query_orders";
};

const CONFIG = {
  search_docs: { label: "Docs lookup", color: "var(--teal)", bg: "var(--teal-soft)" },
  query_orders: { label: "Data query", color: "var(--ochre)", bg: "var(--ochre-soft)" },
};

export function ToolBadge({ tool }: ToolBadgeProps) {
  const cfg = CONFIG[tool];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.color}33`,
        borderRadius: 3,
        padding: "3px 8px",
        transform: "rotate(-0.6deg)",
      }}
    >
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: cfg.color }} />
      {cfg.label}
    </span>
  );
}

export function Citation({ source, section }: { source: string; section: string }) {
  return (
    <div
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 12,
        color: "var(--ink-soft)",
        padding: "6px 10px",
        borderLeft: "2px solid var(--teal)",
        background: "var(--teal-soft)",
        marginTop: 4,
      }}
    >
      {source} <span style={{ opacity: 0.6 }}>§</span> {section}
    </div>
  );
}

export function SqlBlock({ sql }: { sql: string }) {
  return (
    <pre
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 12.5,
        color: "var(--ink)",
        background: "var(--paper-raised)",
        border: "1px solid var(--rule)",
        borderLeft: "2px solid var(--ochre)",
        borderRadius: 3,
        padding: "10px 12px",
        marginTop: 4,
        overflowX: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {sql}
    </pre>
  );
}

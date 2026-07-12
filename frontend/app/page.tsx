import Chat from "@/components/Chat";

export default function Page() {
  return (
    <main
      style={{
        maxWidth: 760,
        margin: "0 auto",
        padding: "40px 20px 80px",
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <header style={{ marginBottom: 28 }}>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--ink-soft)",
            marginBottom: 6,
          }}
        >
          Northwind Gadgets — Support Desk
        </div>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 600,
            fontSize: 32,
            margin: 0,
            fontOpticalSizing: "auto" as any,
          }}
        >
          Ask about an order, or a policy.
        </h1>
        <p style={{ color: "var(--ink-soft)", marginTop: 8, fontSize: 15, lineHeight: 1.5 }}>
          Answers are pulled from our policy documents or the live orders
          ledger — every reply shows exactly where it came from.
        </p>
      </header>
      <Chat />
    </main>
  );
}

"""
Loads orders.csv into a local SQLite DB. This is the table the text-to-SQL
tool queries directly — it is NOT embedded or put anywhere near the vector store.

Run: python ingest/load_orders.py
"""
import os
import sqlite3
import pandas as pd

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "orders.csv")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "orders.db")


def main():
    df = pd.read_csv(CSV_PATH)
    df["order_date"] = pd.to_datetime(df["order_date"]).dt.strftime("%Y-%m-%d")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    df.to_sql("orders", conn, index=False, if_exists="replace",
               dtype={
                   "order_id": "TEXT PRIMARY KEY",
                   "customer": "TEXT",
                   "product": "TEXT",
                   "amount": "REAL",
                   "status": "TEXT",
                   "order_date": "TEXT",  # ISO format, sortable as string
               })
    conn.commit()

    cur = conn.execute("SELECT COUNT(*), MIN(order_date), MAX(order_date) FROM orders")
    count, min_d, max_d = cur.fetchone()
    print(f"Loaded {count} rows into {DB_PATH} (orders table)")
    print(f"Date range: {min_d} to {max_d}")
    print("Columns:", [d[0] for d in conn.execute("SELECT * FROM orders LIMIT 1").description])
    conn.close()


if __name__ == "__main__":
    main()

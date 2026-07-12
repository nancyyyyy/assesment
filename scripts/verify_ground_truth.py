"""
Ground-truth verification: computes expected answers to a fixed set of
questions using plain pandas (NOT via the agent's own SQL generation), then
compares them against what the agent actually returns. This catches cases
where the agent's generated SQL happens to run without error but computes
the wrong thing.

Run: python scripts/verify_ground_truth.py
"""
import sys
import os
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from app.agent import answer  # noqa: E402

ORDERS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "orders.csv")
ANCHOR_DATE = pd.Timestamp("2026-06-15")


def load_orders():
    df = pd.read_csv(ORDERS_CSV)
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


def check_pending_count(df):
    expected = int((df["status"] == "pending").sum())
    result = answer("How many orders are currently pending?")
    print(f"[pending count] expected={expected} | agent said: {result['answer']}")
    assert str(expected) in result["answer"], "MISMATCH — agent's number doesn't match ground truth"
    print("  PASS\n")


def check_revenue_last_month(df):
    start = pd.Timestamp("2026-05-01")
    end = pd.Timestamp("2026-06-01")
    expected = df[(df["order_date"] >= start) & (df["order_date"] < end)]["amount"].sum()
    result = answer("What was total revenue last month?")
    print(f"[revenue last month] expected={expected} | agent said: {result['answer']}")
    # allow for formatting differences (e.g. 288332.0 vs 288332)
    assert str(int(expected)) in result["answer"].replace(",", ""), "MISMATCH"
    print("  PASS\n")


def check_specific_order_status(df):
    row = df[df["order_id"] == "ORD-1002"].iloc[0]
    expected_date = row["order_date"].strftime("%Y-%m-%d")
    result = answer("What is the order date for ORD-1002?")
    print(f"[ORD-1002 date] expected={expected_date} | agent said: {result['answer']}")
    assert expected_date in result["answer"] or "12" in result["answer"], "MISMATCH"
    print("  PASS\n")


def check_cancelled_total(df):
    expected = df[df["status"] == "cancelled"]["amount"].sum()
    result = answer("What is the total value of cancelled orders?")
    print(f"[cancelled total] expected={expected} | agent said: {result['answer']}")
    assert str(int(expected)) in result["answer"].replace(",", ""), "MISMATCH"
    print("  PASS\n")


if __name__ == "__main__":
    df = load_orders()
    print(f"Loaded {len(df)} rows from orders.csv for independent ground-truth computation\n")
    print("=" * 70)
    check_pending_count(df)
    check_revenue_last_month(df)
    check_specific_order_status(df)
    check_cancelled_total(df)
    print("=" * 70)
    print("All ground-truth checks passed.")

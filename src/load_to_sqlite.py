"""
Loads the four synthetic CSVs in data/raw/ into a SQLite database at
data/marketing_finance.db, so sql/business_queries.sql runs against a real,
queryable database rather than being decorative.
"""

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DB_PATH = PROJECT_ROOT / "data" / "marketing_finance.db"

TABLES = {
    "campaigns": "campaigns.csv",
    "customers": "customers.csv",
    "transactions": "transactions.csv",
    "ab_test_campaigns": "ab_test_campaigns.csv",
}

DATE_COLUMNS = {
    "campaigns": ["date"],
    "customers": ["acquisition_date"],
    "transactions": ["transaction_date"],
    "ab_test_campaigns": ["date"],
}


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        for table, filename in TABLES.items():
            df = pd.read_csv(RAW_DIR / filename, parse_dates=DATE_COLUMNS[table])
            for col in DATE_COLUMNS[table]:
                df[col] = df[col].dt.strftime("%Y-%m-%d")
            df.to_sql(table, conn, if_exists="replace", index=False)
            print(f"Loaded {table:<20} {len(df):>7,} rows")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_date ON campaigns(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_channel ON campaigns(channel)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_customer ON transactions(customer_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_channel ON customers(acquisition_channel)")
        conn.commit()
        print("Indexes created.")
    finally:
        conn.close()

    print("Database written to", DB_PATH)


if __name__ == "__main__":
    main()

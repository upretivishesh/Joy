import sqlite3
import pandas as pd

conn = sqlite3.connect("joy.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT,
    mobile TEXT,
    role TEXT,
    industry TEXT,
    score REAL,
    relevant TEXT,
    timestamp TEXT
)
""")
conn.commit()

def save_to_db(df, role, industry):
    for _, row in df.iterrows():
        cursor.execute("""
        INSERT INTO history (name,email,mobile,role,industry,score,relevant,timestamp)
        VALUES (?,?,?,?,?,?,?,datetime('now'))
        """, (
            row["Name"],
            row["Email"],
            row["Mobile"],
            role,
            industry,
            row["Final Score"],
            row["Relevant"]
        ))
    conn.commit()

def load_history():
    return pd.read_sql("SELECT * FROM history ORDER BY timestamp DESC", conn)

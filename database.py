import pandas as pd
import os
import json
from datetime import datetime


def save_to_db(df: pd.DataFrame, role: str, industry: str, user: str):
    path = f"history_{user}.csv"
    df = df.copy()
    df["Role"] = role
    df["Industry"] = industry
    df["Screened At"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    df["Screened By"] = user
    if os.path.exists(path):
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(path, index=False)
    return True


def load_history(user: str) -> pd.DataFrame:
    path = f"history_{user}.csv"
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def clear_history(user: str) -> bool:
    path = f"history_{user}.csv"
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def get_history_stats(user: str) -> dict:
    df = load_history(user)
    if df.empty:
        return {"total": 0, "strong": 0, "roles": []}
    return {
        "total": len(df),
        "strong": len(df[df["Verdict"] == "Strong Fit"]) if "Verdict" in df.columns else 0,
        "roles": df["Role"].unique().tolist() if "Role" in df.columns else []
    }


def save_chat_history(user: str, history: list):
    path = f"chat_{user}.json"
    try:
        with open(path, "w") as f:
            json.dump(history, f)
    except Exception:
        pass


def load_chat_history(user: str) -> list:
    path = f"chat_{user}.json"
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def log_login(user: str):
    path = f"logins_{user}.json"
    entry = {"logged_in_at": datetime.now().strftime("%d %b %Y, %I:%M %p IST")}
    try:
        logs = []
        if os.path.exists(path):
            with open(path, "r") as f:
                logs = json.load(f)
        logs.append(entry)
        with open(path, "w") as f:
            json.dump(logs, f)
    except Exception:
        pass


def load_login_log(user: str) -> list:
    path = f"logins_{user}.json"
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

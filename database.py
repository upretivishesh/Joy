import pandas as pd
import os
from datetime import datetime


def save_to_db(df: pd.DataFrame, role: str, industry: str, user: str):
    """
    Save screening results to a per-user CSV history file.
    Appends to existing history if file exists.
    """
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
    """
    Load full screening history for a user.
    Returns empty DataFrame if no history exists.
    """
    path = f"history_{user}.csv"
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def clear_history(user: str) -> bool:
    """
    Delete history file for a user.
    """
    path = f"history_{user}.csv"
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def get_history_stats(user: str) -> dict:
    """
    Return quick stats about screening history.
    """
    df = load_history(user)
    if df.empty:
        return {"total": 0, "strong": 0, "roles": []}

    return {
        "total": len(df),
        "strong": len(df[df["Verdict"] == "Strong Fit"]) if "Verdict" in df.columns else 0,
        "roles": df["Role"].unique().tolist() if "Role" in df.columns else []
    }

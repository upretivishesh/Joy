import json
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import streamlit as st
except Exception:
    st = None

from .constants import DATA_DIR


HISTORY_COLUMNS = [
    "Send",
    "Duplicate",
    "Profile Key",
    "Name",
    "Email",
    "Phone",
    "Experience",
    "Education",
    "Keyword Score",
    "Semantic Score",
    "Final Score",
    "Verdict",
    "Industry Match",
    "Candidate Industry",
    "Matched Keywords",
    "Missing Keywords",
    "Skills",
    "Reason",
    "Source File",
    "AI Used",
    "Keywords Used",
    "Role",
    "JD",
    "Feedback",
    "Saved At",
]

JD_LIBRARY_COLUMNS = [
    "Role",
    "JD Text",
    "Tags",
    "Saved At",
]


def _safe_user_key(user_key: str) -> str:
    value = (user_key or "local").strip().lower()
    keep = []
    for ch in value:
        if ch.isalnum() or ch in {"@", ".", "_", "-"}:
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep) or "local"


def _history_dir() -> Path:
    base = Path(DATA_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _history_path(user_key: str) -> Path:
    return _history_dir() / f"history_{_safe_user_key(user_key)}.csv"


def _jd_library_path(user_key: str) -> Path:
    return _history_dir() / f"jd_library_{_safe_user_key(user_key)}.csv"


def _ensure_history_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in HISTORY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df.loc[:, ~df.columns.duplicated()]
    return df[HISTORY_COLUMNS]


def _ensure_jd_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in JD_LIBRARY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df.loc[:, ~df.columns.duplicated()]
    return df[JD_LIBRARY_COLUMNS]


def load_history(user_key: str) -> pd.DataFrame:
    path = _history_path(user_key)
    if not path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    df = _ensure_history_columns(df)
    return df


def save_history(results_df: pd.DataFrame, role: str, user_key: str, jd_text: str = "") -> bool:
    try:
        existing = load_history(user_key)
        incoming = results_df.copy()

        incoming["Role"] = role or ""
        incoming["JD"] = jd_text or ""
        incoming["Feedback"] = incoming.get("Feedback", "Pending")
        incoming["Feedback"] = incoming["Feedback"].replace("", "Pending").fillna("Pending")
        incoming["Saved At"] = datetime.now().isoformat(timespec="seconds")

        incoming = _ensure_history_columns(incoming)

        if not existing.empty:
            combined = pd.concat([existing, incoming], ignore_index=True)
        else:
            combined = incoming.copy()

        combined = combined.loc[:, ~combined.columns.duplicated()]

        dedupe_keys = [c for c in ["Profile Key", "Role", "Source File"] if c in combined.columns]
        if dedupe_keys:
            combined = combined.drop_duplicates(subset=dedupe_keys, keep="last")
        else:
            combined = combined.drop_duplicates(keep="last")

        combined.to_csv(_history_path(user_key), index=False)
        return True
    except Exception:
        return False


def clear_history(user_key: str) -> bool:
    try:
        path = _history_path(user_key)
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


def clear_role_history(user_key: str, role: str) -> bool:
    try:
        df = load_history(user_key)
        if df.empty or "Role" not in df.columns:
            return True

        remaining = df[df["Role"].astype(str) != str(role)]
        remaining = _ensure_history_columns(remaining)
        remaining.to_csv(_history_path(user_key), index=False)
        return True
    except Exception:
        return False


def confirm_delete_role_history(user_key: str, role: str):
    ok = clear_role_history(user_key, role)
    if st is not None:
        if ok:
            st.success(f"Deleted all history for {role}")
        else:
            st.error(f"Could not delete history for {role}")
        st.rerun()


def confirm_delete_all_history(user_key: str):
    ok = clear_history(user_key)
    if st is not None:
        if ok:
            st.success("Deleted all screening history")
        else:
            st.error("Could not delete history")
        st.rerun()


def update_feedback(user_key: str, profile_key_value: str, role: str, feedback: str) -> bool:
    try:
        df = load_history(user_key)
        if df.empty:
            return False

        profile_key_value = str(profile_key_value or "").strip()
        role = str(role or "").strip()
        feedback = str(feedback or "").strip() or "Pending"

        mask = pd.Series([True] * len(df))

        if "Profile Key" in df.columns and profile_key_value:
            mask = mask & (df["Profile Key"].astype(str).str.strip() == profile_key_value)

        if "Role" in df.columns and role:
            mask = mask & (df["Role"].astype(str).str.strip() == role)

        if not mask.any():
            return False

        df.loc[mask, "Feedback"] = feedback
        df = _ensure_history_columns(df)
        df.to_csv(_history_path(user_key), index=False)
        return True
    except Exception:
        return False


def load_jd_library(user_key: str) -> pd.DataFrame:
    path = _jd_library_path(user_key)
    if not path.exists():
        return pd.DataFrame(columns=JD_LIBRARY_COLUMNS)

    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=JD_LIBRARY_COLUMNS)

    df = _ensure_jd_columns(df)
    df = df.sort_values("Saved At", ascending=False, na_position="last").reset_index(drop=True)
    return df


def save_jd(user_key: str, role: str, jd_text: str, tags: str = "") -> bool:
    try:
        role = str(role or "").strip()
        jd_text = str(jd_text or "").strip()
        tags = str(tags or "").strip()

        if not role or not jd_text:
            return False

        existing = load_jd_library(user_key)
        new_row = pd.DataFrame(
            [{
                "Role": role,
                "JD Text": jd_text,
                "Tags": tags,
                "Saved At": datetime.now().isoformat(timespec="seconds"),
            }]
        )

        combined = pd.concat([existing, new_row], ignore_index=True)
        combined = _ensure_jd_columns(combined)
        combined.to_csv(_jd_library_path(user_key), index=False)
        return True
    except Exception:
        return False


def delete_jd(user_key: str, role: str, saved_at: str = "") -> bool:
    try:
        df = load_jd_library(user_key)
        if df.empty:
            return False

        role = str(role or "").strip()
        saved_at = str(saved_at or "").strip()

        if saved_at:
            mask = ~(
                (df["Role"].astype(str).str.strip() == role)
                & (df["Saved At"].astype(str).str.strip() == saved_at)
            )
        else:
            mask = ~(df["Role"].astype(str).str.strip() == role)

        remaining = df[mask].copy()
        remaining = _ensure_jd_columns(remaining)
        remaining.to_csv(_jd_library_path(user_key), index=False)
        return True
    except Exception:
        return False


def confirm_delete_jd(user_key: str, role: str, saved_at: str = ""):
    ok = delete_jd(user_key, role, saved_at)
    if st is not None:
        if ok:
            st.success(f"Deleted JD: {role}")
        else:
            st.error(f"Could not delete JD: {role}")
        st.rerun()

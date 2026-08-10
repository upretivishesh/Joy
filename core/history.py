# core/history.py
import pandas as pd
import numpy as np
import json
import os
import re
from typing import Optional

from .constants import DATA_DIR
from .parser import profile_key
from .utils import safe_filename_part

try:
    import streamlit as st
except ImportError:
    st = None

from supabase import create_client, Client


def _get_supabase_client() -> Optional[Client]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if (not url or not key) and st is not None:
        try:
            url = url or st.secrets.get("SUPABASE_URL")
            key = key or st.secrets.get("SUPABASE_KEY")
        except Exception:
            pass

    if url and key:
        try:
            return create_client(url, key)
        except Exception as e:
            print(f"Supabase connection failed: {e}")
    return None


supabase: Optional[Client] = _get_supabase_client()


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    return value


def _row_to_safe_dict(row: pd.Series) -> dict:
    raw = row.to_dict()
    safe = {k: _json_safe(v) for k, v in raw.items()}
    return json.loads(json.dumps(safe, default=str))


def _clean_phone_value(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    text = re.sub(r"\.0(?=\D|$)", "", text)
    return text


def _clean_phone_column(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Phone" not in df.columns:
        return df
    df = df.copy()
    df["Phone"] = df["Phone"].apply(_clean_phone_value)
    return df


def history_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"candidate_history_{safe_filename_part(user_key)}.xlsx"


def legacy_history_path(user_key: str):
    return DATA_DIR / f"history_{safe_filename_part(user_key)}.csv"


def jd_library_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"jd_library_{safe_filename_part(user_key)}.xlsx"


def load_history(user_key: str) -> pd.DataFrame:
    if supabase:
        try:
            response = (
                supabase.table("screening_history")
                .select("*")
                .eq("user_key", user_key)
                .order("created_at", desc=True)
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                # Rename columns to match your original style
                rename_map = {
                    "final_score": "Final Score",
                    "industry_match": "Industry Match",
                    "candidate_industry": "Candidate Industry",
                    "matched_keywords": "Matched Keywords",
                    "missing_keywords": "Missing Keywords",
                    "source_file": "Source File",
                    "profile_key": "Profile Key",
                }
                df = df.rename(columns=rename_map)
                return _clean_phone_column(df)
        except Exception as e:
            print(f"Supabase load_history error: {e}")

    # Fallback to local
    path = history_path(user_key)
    if path.exists():
        return _clean_phone_column(pd.read_excel(path))
    return pd.DataFrame()

def _ensure_profile_key(df: pd.DataFrame) -> pd.DataFrame:
    if "Profile Key" not in df.columns:
        df["Profile Key"] = df.apply(
            lambda row: profile_key(
                str(row.get("Name", "")),
                str(row.get("Email", "")),
                str(row.get("Phone", "")),
            ),
            axis=1,
        )
    return df


def save_history(df: pd.DataFrame, role: str, user_key: str, jd_text: str = "") -> None:
    if df.empty:
        return

    to_save = df.copy()
    to_save["Role"] = role
    to_save["JD"] = jd_text
    to_save = _clean_phone_column(to_save)
    to_save = _ensure_profile_key(to_save)

    if supabase:
        records = []
        for _, row in to_save.iterrows():
            records.append({
                "user_key": user_key,
                "role": role,
                "profile_key": str(row.get("Profile Key", "")),
                "name": str(row.get("Name", "")),
                "email": str(row.get("Email", "")),
                "phone": str(row.get("Phone", "")),
                "experience": float(row.get("Experience", 0) or 0),
                "education": str(row.get("Education", "")),
                "final_score": float(row.get("Final Score", 0) or 0),
                "verdict": str(row.get("Verdict", "")),
                "industry_match": str(row.get("Industry Match", "")),
                "candidate_industry": str(row.get("Candidate Industry", "")),
                "matched_keywords": str(row.get("Matched Keywords", "")),
                "missing_keywords": str(row.get("Missing Keywords", "")),
                "skills": str(row.get("Skills", "")),
                "reason": str(row.get("Reason", "")),
                "feedback": str(row.get("Feedback", "Pending")),
                "client": str(row.get("Client", "")),
                "source_file": str(row.get("Source File", "")),
                "jd": (jd_text or "")[:4000],
            })
        try:
            supabase.table("screening_history").insert(records).execute()
            print(f"✅ History saved to Supabase ({len(records)} rows)")
            return
        except Exception as e:
            print(f"❌ Supabase save_history failed: {e}")

    # Fallback local save
    path = history_path(user_key)
    DATA_DIR.mkdir(exist_ok=True)
    to_save.to_excel(path, index=False)
    print(f"✅ History saved locally")


def clear_history(user_key: str) -> None:
    """Delete ALL history for a user"""
    if supabase:
        try:
            supabase.table("screening_history").delete().eq("user_key", user_key).execute()
            print(f"✅ All history deleted from Supabase for {user_key}")
            return
        except Exception as e:
            print(f"❌ Supabase clear_history error: {e}")

    # Fallback local
    for path in [history_path(user_key), legacy_history_path(user_key)]:
        if path.exists():
            path.unlink()
            print(f"✅ Local history file deleted: {path}")


def clear_role_history(user_key: str, role: str) -> None:
    """Delete all history for a specific role"""
    if not role:
        return

    if supabase:
        try:
            supabase.table("screening_history")\
                .delete()\
                .eq("user_key", user_key)\
                .eq("role", role)\
                .execute()
            print(f"✅ Deleted history for role '{role}' from Supabase")
            return
        except Exception as e:
            print(f"❌ Supabase clear_role_history error: {e}")

    # Fallback local
    path = history_path(user_key)
    if path.exists():
        try:
            df = pd.read_excel(path)
            if "Role" in df.columns:
                df = df[df["Role"].astype(str) != str(role)]
                df = _clean_phone_column(df)
                df.to_excel(path, index=False)
                print(f"✅ Deleted local history for role: {role}")
        except Exception as e:
            print(f"❌ Local clear_role_history error: {e}")


def mark_batch_duplicates(rows: list[dict]) -> list[dict]:
    seen = set()
    for row in rows:
        key = str(row.get("Profile Key", ""))
        row["Duplicate"] = bool(key and key in seen)
        if key:
            seen.add(key)
    return rows


def search_candidates(user_key: str, query: str) -> pd.DataFrame:
    hist = load_history(user_key)
    if hist.empty or not query.strip():
        return hist.iloc[0:0] if not hist.empty else pd.DataFrame()

    q = query.strip().lower()
    search_cols = [c for c in ["Name", "Email", "Phone", "Profile Key"] if c in hist.columns]

    if not search_cols:
        return hist.iloc[0:0]

    mask = pd.Series(False, index=hist.index)
    for col in search_cols:
        mask |= hist[col].astype(str).str.lower().str.contains(q, na=False)

    matches = hist[mask].copy()
    if "Screened At" in matches.columns:
        matches = matches.sort_values("Screened At", ascending=False)
    return matches


def filter_history_by_search(hist: pd.DataFrame, query: str) -> pd.DataFrame:
    if hist.empty or not query.strip():
        return hist

    q = query.strip().lower()
    search_cols = [c for c in ["Name", "Email", "Phone", "Profile Key", "Role"] if c in hist.columns]

    if not search_cols:
        return hist.iloc[0:0]

    mask = pd.Series(False, index=hist.index)
    for col in search_cols:
        mask |= hist[col].astype(str).str.lower().str.contains(q, na=False)

    return hist[mask]


def load_jd_library(user_key: str) -> pd.DataFrame:
    if supabase:
        try:
            response = (
                supabase.table("jd_library")
                .select("*")
                .eq("user_key", user_key)
                .order("created_at", desc=True)
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(columns={
                    "role": "Role",
                    "jd_text": "JD Text",
                    "tags": "Tags",
                    "created_at": "Saved At"
                })
                return df[["Role", "JD Text", "Saved At", "Tags"]]
        except Exception as e:
            print(f"Supabase load_jd_library error: {e}")

    # Fallback
    path = jd_library_path(user_key)
    if path.exists():
        return pd.read_excel(path)
    return pd.DataFrame(columns=["Role", "JD Text", "Saved At", "Tags"])

def save_history(df: pd.DataFrame, role: str, user_key: str, jd_text: str = "") -> bool:
    """
    Returns True if saved successfully (Supabase or local), False otherwise.
    """
    if df is None or df.empty:
        return False

    to_save = df.copy()
    to_save["Role"] = role
    to_save["JD"] = jd_text
    to_save = _clean_phone_column(to_save)
    to_save = _ensure_profile_key(to_save)

    # ---------- Supabase ----------
    if supabase:
        records = []
        for _, row in to_save.iterrows():
            records.append({
                "user_key": user_key,
                "role": str(role),
                "profile_key": str(row.get("Profile Key", "")),
                "name": str(row.get("Name", "")),
                "email": str(row.get("Email", "")),
                "phone": str(row.get("Phone", "")),
                "experience": float(row.get("Experience", 0) or 0),
                "education": str(row.get("Education", "")),
                "final_score": float(row.get("Final Score", 0) or 0),
                "verdict": str(row.get("Verdict", "")),
                "industry_match": str(row.get("Industry Match", "")),
                "candidate_industry": str(row.get("Candidate Industry", "")),
                "matched_keywords": str(row.get("Matched Keywords", "")),
                "missing_keywords": str(row.get("Missing Keywords", "")),
                "skills": str(row.get("Skills", "")),
                "reason": str(row.get("Reason", "")),
                "feedback": str(row.get("Feedback", "Pending") or "Pending"),
                "client": str(row.get("Client", "") or row.get("client_company", "")),
                "source_file": str(row.get("Source File", "")),
                "jd": (jd_text or "")[:4000],
            })

        try:
            # Use upsert so re-screening the same people doesn't crash
            # (requires a unique constraint on user_key + profile_key + role)
            supabase.table("screening_history").upsert(
                records,
                on_conflict="user_key,profile_key,role"   # adjust if your unique key is different
            ).execute()
            print(f"✅ History saved to Supabase ({len(records)} rows)")
            return True
        except Exception as e:
            print(f"❌ Supabase save_history failed: {e}")
            # fall through to local

    # ---------- Local fallback ----------
    try:
        path = history_path(user_key)
        DATA_DIR.mkdir(exist_ok=True)

        existing = pd.DataFrame()
        if path.exists():
            existing = pd.read_excel(path)

        combined = pd.concat([existing, to_save], ignore_index=True)
        # optional: drop exact duplicates
        if "Profile Key" in combined.columns and "Role" in combined.columns:
            combined = combined.drop_duplicates(
                subset=["Profile Key", "Role"], keep="last"
            )

        combined.to_excel(path, index=False)
        print(f"✅ History saved locally → {path}")
        return True
    except Exception as e:
        print(f"❌ Local save_history failed: {e}")
        return False

def delete_jd(user_key: str, role: str) -> None:
    """Delete a specific JD from the library"""
    if not role:
        return

    if supabase:
        try:
            supabase.table("jd_library")\
                .delete()\
                .eq("user_key", user_key)\
                .eq("role", role.strip())\
                .execute()
            print(f"✅ Deleted JD from Supabase: {role}")
            return
        except Exception as e:
            print(f"❌ Supabase delete_jd error: {e}")

    # Fallback local
    path = jd_library_path(user_key)
    if path.exists():
        try:
            df = pd.read_excel(path)
            if "Role" in df.columns:
                df = df[df["Role"].astype(str).str.lower().str.strip() != role.lower().strip()]
                df.to_excel(path, index=False)
                print(f"✅ Deleted JD locally: {role}")
        except Exception as e:
            print(f"❌ Local delete_jd error: {e}")

def get_jd(user_key: str, role: str) -> str:
    df = load_jd_library(user_key)
    if df.empty or "Role" not in df.columns:
        return ""
    match = df[df["Role"].astype(str).str.lower().str.strip() == role.lower().strip()]
    if match.empty:
        return ""
    return str(match.iloc[-1].get("JD Text", ""))


def update_feedback(user_key: str, profile_key_value: str, role: str, feedback: str) -> bool:
    """Update feedback for a specific candidate + role"""
    if not profile_key_value or not role:
        return False

    if supabase:
        try:
            # Update the matching row
            result = (
                supabase.table("screening_history")
                .update({"feedback": feedback})
                .eq("user_key", user_key)
                .eq("profile_key", str(profile_key_value))
                .eq("role", role)
                .execute()
            )
            if result.data:
                print(f"✅ Feedback updated in Supabase: {feedback}")
                return True
            else:
                print("No matching record found in Supabase for feedback update")
        except Exception as e:
            print(f"❌ Supabase update_feedback error: {e}")

    # Fallback to local file
    path = history_path(user_key)
    if path.exists():
        try:
            df = pd.read_excel(path)
            if "Profile Key" not in df.columns or "Role" not in df.columns:
                return False

            mask = (
                (df["Profile Key"].astype(str) == str(profile_key_value))
                & (df["Role"].astype(str) == str(role))
            )
            if not mask.any():
                return False

            if "Feedback" not in df.columns:
                df["Feedback"] = "Pending"

            df.loc[mask, "Feedback"] = feedback
            df = _clean_phone_column(df)
            df.to_excel(path, index=False)
            return True
        except Exception as e:
            print(f"❌ Local update_feedback error: {e}")
            return False

    return False

def confirm_delete_all_history(user_key: str):
    clear_history(user_key)
    st.success("All history has been deleted")
    st.rerun()


def confirm_delete_role_history(user_key: str, role: str):
    clear_role_history(user_key, role)
    st.success(f"Deleted all history for role: **{role}**")
    st.rerun()


def confirm_delete_jd(user_key: str, role: str):
    delete_jd(user_key, role)
    st.success(f"Deleted JD: **{role}**")
    st.rerun()

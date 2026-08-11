# core/history.py
import pandas as pd
import numpy as np
import json
import os
from typing import Optional

from .constants import DATA_DIR
from .parser import profile_key
from .utils import safe_filename_part


# ─── Safe Supabase Initialization ───────────────────────────────────────────
try:
    import streamlit as st
except ImportError:
    st = None

from supabase import create_client, Client


def _get_supabase_client() -> Optional[Client]:
    """Safely get Supabase client. Never crashes on import."""
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
    return None


def _json_safe(value):
    """Convert a single value into something json.dumps / PostgREST can accept."""
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
    """Turn a pandas row into a plain, JSON-serializable dict for Supabase JSONB."""
    raw = row.to_dict()
    safe = {k: _json_safe(v) for k, v in raw.items()}
    return json.loads(json.dumps(safe, default=str))


def history_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"candidate_history_{safe_filename_part(user_key)}.xlsx"


def legacy_history_path(user_key: str):
    return DATA_DIR / f"history_{safe_filename_part(user_key)}.csv"


def jd_library_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"jd_library_{safe_filename_part(user_key)}.xlsx"


# ─── Candidate History functions ────────────────────────────────────────────
def load_history(user_key: str) -> pd.DataFrame:

    supabase = _get_supabase_client()
    if supabase:
        try:
            response = supabase.table("candidate_history").select("data").eq("user_key", user_key).execute()
            if response.data:
                records = [row["data"] for row in response.data]
                return pd.DataFrame(records)
            return pd.DataFrame()
        except Exception as e:
            print(f"Supabase load_history error: {e}")

    path = history_path(user_key)
    if path.exists():
        return pd.read_excel(path)
    legacy = legacy_history_path(user_key)
    if legacy.exists():
        return pd.read_csv(legacy)
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


def save_history(df: pd.DataFrame, role: str, user_key: str, jd_text: str = "") -> bool:
    """
    Save screening results to Supabase (screening_history) and to local Excel.
    Returns True if at least one of them succeeds.
    """
    if df is None or df.empty:
        print("[save_history] skipped: empty df")
        return False

    to_save = df.copy()
    to_save["Role"] = role
    to_save["JD"] = jd_text
    to_save = _clean_phone_column(to_save)
    to_save = _ensure_profile_key(to_save)

    supabase_ok = False

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
            # NOTE: this requires a UNIQUE constraint on (user_key, profile_key, role)
            supabase.table("screening_history").upsert(
                records,
                on_conflict="user_key,profile_key,role",
            ).execute()
            print(f"✅ save_history Supabase ok — {len(records)} rows")
            supabase_ok = True
        except Exception as e:
            print(f"❌ save_history Supabase failed: {e}")

    # Local Excel save (always try)
    local_ok = False
    try:
        DATA_DIR.mkdir(exist_ok=True)
        path = history_path(user_key)
        existing = pd.DataFrame()
        if path.exists():
            existing = pd.read_excel(path)

        combined = pd.concat([existing, to_save], ignore_index=True)
        if "Profile Key" in combined.columns and "Role" in combined.columns:
            combined = combined.drop_duplicates(subset=["Profile Key", "Role"], keep="last")

        combined.to_excel(path, index=False)
        print(f"✅ save_history local ok → {path}")
        local_ok = True
    except Exception as e:
        print(f"❌ save_history local failed: {e}")

    return supabase_ok or local_ok


def clear_history(user_key: str) -> None:

    supabase = _get_supabase_client()
    if supabase:
        try:
            supabase.table("candidate_history").delete().eq("user_key", user_key).execute()
            return
        except Exception as e:
            print(f"Supabase clear_history error: {e}")

    for path in [history_path(user_key), legacy_history_path(user_key)]:
        if path.exists():
            path.unlink()


def clear_role_history(user_key: str, role: str) -> None:

    supabase = _get_supabase_client()
    """
    Delete all history for a single role. Transaction-safe: re-inserts the
    kept records BEFORE deleting the old ones, so a network failure never
    leaves the user with zero history for every role.
    """
    if supabase:
        try:
            response = supabase.table("candidate_history").select("*").eq("user_key", user_key).execute()
            all_records = response.data or []

            kept_records = []
            target_ids = []
            for record in all_records:
                data = record.get("data", {}) or {}
                stored_role = str(data.get("Role", "")).strip().lower()
                if stored_role == role.strip().lower():
                    target_ids.append(record["id"])
                else:
                    kept_records.append(record)

            if not target_ids:
                print(f"No records found for role: '{role}'")
                return

            # Delete only the target role's rows directly — no destructive
            # delete-everything-then-reinsert step, so a failure mid-way
            # cannot wipe unrelated history.
            for rid in target_ids:
                supabase.table("candidate_history").delete().eq("id", rid).execute()

            print(f"✅ Successfully deleted history for role: '{role}' (kept {len(kept_records)} records)")
            return

        except Exception as e:
            print(f"❌ Supabase clear_role_history error: {e}")

    path = history_path(user_key)
    if not path.exists():
        legacy = legacy_history_path(user_key)
        if not legacy.exists():
            return
        df = pd.read_csv(legacy)
        write_excel = False
    else:
        df = pd.read_excel(path)
        write_excel = True

    if "Role" not in df.columns:
        return
    df = df[df["Role"].astype(str) != str(role)]
    if write_excel:
        df.to_excel(path, index=False)
    else:
        df.to_csv(legacy_history_path(user_key), index=False)


def mark_batch_duplicates(rows: list[dict]) -> list[dict]:
    seen = set()
    for row in rows:
        key = str(row.get("Profile Key", ""))
        row["Duplicate"] = bool(key and key in seen)
        if key:
            seen.add(key)
    return rows


def search_candidates(user_key: str, query: str) -> pd.DataFrame:
    """
    Search every candidate ever screened for this user by name, email, or
    phone — regardless of role. Case-insensitive, partial match supported.
    This is the backbone of "remember every candidate forever": a recruiter
    can look up a candidate's full history across every role/client they've
    ever been screened for.
    """
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
    """
    Backward-compatible wrapper matching the existing import used in app.py
    (from core.history import filter_history_by_search). Filters an
    already-loaded history DataFrame by name, email, or phone.
    """
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


# ─── JD Library functions ───────────────────────────────────────────────────
def load_jd_library(user_key: str) -> pd.DataFrame:

    supabase = _get_supabase_client()
    if supabase:
        try:
            response = supabase.table("jd_library").select("*").eq("user_key", user_key).execute()
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(columns={
                    "role": "Role", "jd_text": "JD Text",
                    "saved_at": "Saved At", "tags": "Tags"
                })
                return df[["Role", "JD Text", "Saved At", "Tags"]]
            return pd.DataFrame(columns=["Role", "JD Text", "Saved At", "Tags"])
        except Exception as e:
            print(f"Supabase load_jd_library error: {e}")

    path = jd_library_path(user_key)
    if path.exists():
        return pd.read_excel(path)
    return pd.DataFrame(columns=["Role", "JD Text", "Saved At", "Tags"])


def save_jd(user_key: str, role: str, jd_text: str, tags: str = "") -> bool:
    if not jd_text.strip() or not role.strip():
        return False

    supabase = _get_supabase_client()

    if supabase:
        try:
            data = {
                "user_key": user_key,
                "role": role.strip(),
                "jd_text": jd_text.strip(),
                "saved_at": pd.Timestamp.now().isoformat(),
                "tags": tags.strip(),
            }
            # Prefer upsert if unique constraint exists; plain insert is safer if not
            supabase.table("jd_library").upsert(
                data, on_conflict="user_key,role"
            ).execute()
            return True
        except Exception as e:
            print(f"Supabase save_jd error: {e}")
            # fall through to local save

    try:
        DATA_DIR.mkdir(exist_ok=True)
        existing = load_jd_library(user_key)
        # If load_jd_library also hits broken Supabase, force empty frame
        if existing is None or not isinstance(existing, pd.DataFrame):
            existing = pd.DataFrame(columns=["Role", "JD Text", "Saved At", "Tags"])

        new_entry = pd.DataFrame([{
            "Role": role.strip(),
            "JD Text": jd_text.strip(),
            "Saved At": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Tags": tags.strip(),
        }])

        if not existing.empty and "Role" in existing.columns:
            existing = existing[
                existing["Role"].astype(str).str.lower().str.strip()
                != role.lower().strip()
            ]

        combined = pd.concat([existing, new_entry], ignore_index=True)
        combined.to_excel(jd_library_path(user_key), index=False)
        print(f"✅ JD saved locally for user: {user_key}")
        return True
    except Exception as e:
        print(f"❌ Local save_jd also failed: {e}")
        return False


def delete_jd(user_key: str, role: str) -> None:

    supabase = _get_supabase_client()
    if supabase:
        try:
            supabase.table("jd_library").delete().eq("user_key", user_key).ilike("role", role.strip()).execute()
            print(f"✅ Deleted JD: {role}")
            return
        except Exception as e:
            print(f"Supabase delete_jd error: {e}")

    path = jd_library_path(user_key)
    if not path.exists():
        return
    df = pd.read_excel(path)
    if "Role" not in df.columns:
        return
    df = df[df["Role"].astype(str).str.lower().str.strip() != role.lower().strip()]
    df.to_excel(path, index=False)


def get_jd(user_key: str, role: str) -> str:
    df = load_jd_library(user_key)
    if df.empty or "Role" not in df.columns:
        return ""
    match = df[df["Role"].astype(str).str.lower().str.strip() == role.lower().strip()]
    if match.empty:
        return ""
    return str(match.iloc[-1].get("JD Text", ""))


def update_feedback(user_key: str, profile_key_value: str, role: str, feedback: str) -> bool:

    supabase = _get_supabase_client()
    """
    Tag a specific candidate history record with outcome feedback (Good Hire /
    Bad Hire / Not Selected / Pending). This is step one of Joy learning from
    real outcomes over time — it just captures the signal for now. Stored
    inside the existing JSONB 'data' blob each history row already uses, so
    it needs no new Supabase columns or migration.
    """
    if not supabase:
        return False
    if not profile_key_value:
        return False
    try:
        response = (
            supabase.table("candidate_history")
            .select("id, data")
            .eq("user_key", user_key)
            .eq("role", role)
            .execute()
        )
        for row in response.data or []:
            data = row.get("data", {}) or {}
            if str(data.get("Profile Key", "")) == str(profile_key_value):
                data["Feedback"] = feedback
                supabase.table("candidate_history").update({"data": data}).eq("id", row["id"]).execute()
                return True
        return False
    except Exception as e:
        print(f"❌ Supabase update_feedback error: {e}")
        return False


def confirm_delete_role_history(user_key: str, role: str):
    clear_role_history(user_key, role)
    st.success(f"Deleted all history for role: {role}")
    st.rerun()


def confirm_delete_all_history(user_key: str):
    clear_history(user_key)
    st.success("All history has been deleted")
    st.rerun()


def confirm_delete_jd(user_key: str, role: str):
    delete_jd(user_key, role)
    st.success(f"Deleted JD: {role}")
    st.rerun()

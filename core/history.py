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

    # Only try st.secrets if we're inside a Streamlit context
    if (not url or not key) and st is not None:
        try:
            url = url or st.secrets.get("SUPABASE_URL")
            key = key or st.secrets.get("SUPABASE_KEY")
        except Exception:
            # No secrets file found or not running via streamlit run
            pass

    if url and key:
        try:
            return create_client(url, key)
        except Exception as e:
            print(f"Supabase connection failed: {e}")
            return None
    return None


supabase: Optional[Client] = _get_supabase_client()


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
    # Final guard: round-trip through json to catch anything still non-serializable
    return json.loads(json.dumps(safe, default=str))


# ─── Rest of the file (same as before) ──────────────────────────────────────
def history_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"candidate_history_{safe_filename_part(user_key)}.xlsx"


def legacy_history_path(user_key: str):
    return DATA_DIR / f"history_{safe_filename_part(user_key)}.csv"


def jd_library_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"jd_library_{safe_filename_part(user_key)}.xlsx"


# ─── Candidate History functions (unchanged logic) ──────────────────────────
def load_history(user_key: str) -> pd.DataFrame:
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


def save_history(df: pd.DataFrame, role: str, user_key: str, jd_text: str = "") -> None:
    if df.empty:
        print("save_history skipped: DataFrame is empty")
        return

    batch = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    to_save = df.copy()
    to_save["Role"] = role
    to_save["JD"] = jd_text
    to_save["Screened At"] = batch

    if "Profile Key" not in to_save.columns:
        to_save["Profile Key"] = to_save.apply(
            lambda row: profile_key(
                str(row.get("Name", "")),
                str(row.get("Email", "")),
                str(row.get("Phone", "")),
            ),
            axis=1,
        )

    old = load_history(user_key)

    if not old.empty:
        if "Profile Key" not in old.columns:
            old["Profile Key"] = old.apply(
                lambda row: profile_key(
                    str(row.get("Name", "")),
                    str(row.get("Email", "")),
                    str(row.get("Phone", "")),
                ),
                axis=1,
            )
        seen = set(old["Profile Key"].dropna().astype(str))
        to_save["Duplicate"] = to_save["Profile Key"].astype(str).isin(seen)
        combined = pd.concat([old, to_save], ignore_index=True)
    else:
        to_save["Duplicate"] = to_save.duplicated("Profile Key", keep="first")
        combined = to_save

    combined = combined.loc[:, ~combined.columns.duplicated()].fillna("")
    if "Profile Key" in combined.columns:
        combined = combined.drop_duplicates(subset=["Profile Key", "Role"], keep="last")

    saved = False

    # === Supabase path (now using safe JSON conversion) ===
    if supabase:
        try:
            supabase.table("candidate_history").delete().eq("user_key", user_key).execute()

            records = []
            for _, row in combined.iterrows():
                safe_data = _row_to_safe_dict(row)          # ← This is the fix
                records.append({
                    "user_key": user_key,
                    "role": role,
                    "jd_text": jd_text,
                    "screened_at": batch,
                    "data": safe_data
                })

            if records:
                supabase.table("candidate_history").insert(records).execute()

            print(f"✅ History saved to Supabase for user: {user_key}")
            saved = True

        except Exception as e:
            print(f"❌ Supabase save_history failed: {e}")

    # === Local fallback ===
    if not saved:
        try:
            DATA_DIR.mkdir(exist_ok=True)
            combined.to_excel(history_path(user_key), index=False)
            print(f"✅ History saved locally to Excel for user: {user_key}")
        except Exception as e:
            print(f"❌ Local save also failed: {e}")


def clear_history(user_key: str) -> None:
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
    if supabase:
        try:
            # 1. Fetch all records for this user
            response = supabase.table("candidate_history").select("*").eq("user_key", user_key).execute()
            all_records = response.data or []

            # 2. Keep only the records whose Role does NOT match
            kept_records = []
            for record in all_records:
                data = record.get("data", {})
                stored_role = str(data.get("Role", "")).strip().lower()
                if stored_role != role.strip().lower():
                    kept_records.append(record)

            # 3. Delete ALL records for this user
            supabase.table("candidate_history").delete().eq("user_key", user_key).execute()

            # 4. Re-insert only the records we want to keep
            if kept_records:
                to_insert = []
                for rec in kept_records:
                    to_insert.append({
                        "user_key": rec["user_key"],
                        "role": rec.get("role"),
                        "jd_text": rec.get("jd_text"),
                        "screened_at": rec.get("screened_at"),
                        "data": rec.get("data")
                    })
                supabase.table("candidate_history").insert(to_insert).execute()

            print(f"✅ Successfully deleted history for role: '{role}' (kept {len(kept_records)} records)")
            return

        except Exception as e:
            print(f"❌ Supabase clear_role_history error: {e}")

    # === Local file fallback (unchanged) ===
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


# ─── JD Library functions ───────────────────────────────────────────────────
def load_jd_library(user_key: str) -> pd.DataFrame:
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

    if supabase:
        try:
            data = {
                "user_key": user_key,
                "role": role.strip(),
                "jd_text": jd_text.strip(),
                "saved_at": pd.Timestamp.now().isoformat(),
                "tags": tags.strip()
            }
            supabase.table("jd_library").upsert(data, on_conflict="user_key,role").execute()
            return True
        except Exception as e:
            print(f"Supabase save_jd error: {e}")
            return False

    DATA_DIR.mkdir(exist_ok=True)
    existing = load_jd_library(user_key)
    new_entry = pd.DataFrame([{
        "Role": role.strip(),
        "JD Text": jd_text.strip(),
        "Saved At": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Tags": tags.strip(),
    }])
    if not existing.empty and "Role" in existing.columns:
        existing = existing[existing["Role"].astype(str).str.lower().str.strip() != role.lower().strip()]
    combined = pd.concat([existing, new_entry], ignore_index=True)
    combined.to_excel(jd_library_path(user_key), index=False)
    return True


def delete_jd(user_key: str, role: str) -> None:
    if supabase:
        try:
            supabase.table("jd_library").delete().eq("user_key", user_key).ilike("role", role.strip()).execute()
            print(f"✅ Deleted JD: {role}")
            return
        except Exception as e:
            print(f"Supabase delete_jd error: {e}")

    # Local fallback
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

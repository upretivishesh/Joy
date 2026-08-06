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
                supabase.table("candidate_history")
                .select("data")
                .eq("user_key", user_key)
                .execute()
            )
            if response.data:
                records = [row["data"] for row in response.data]
                df = pd.DataFrame(records)
                return _clean_phone_column(df)
            return pd.DataFrame()
        except Exception as e:
            print(f"Supabase load_history error: {e}")

    path = history_path(user_key)
    if path.exists():
        print(f"[load_history] reading {path}")
        return _clean_phone_column(pd.read_excel(path))
    legacy = legacy_history_path(user_key)
    if legacy.exists():
        print(f"[load_history] reading legacy {legacy}")
        return _clean_phone_column(pd.read_csv(legacy))
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
        print("save_history skipped: DataFrame is empty")
        return

    batch = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[save_history] user_key={user_key}, role={role}, rows={len(df)}, batch={batch}")

    to_save = df.copy()
    to_save["Role"] = role
    to_save["JD"] = jd_text
    to_save["Screened At"] = batch
    to_save = _clean_phone_column(to_save)
    to_save = _ensure_profile_key(to_save)

    old = load_history(user_key)
    if not old.empty:
        old = _ensure_profile_key(old)

    if "Feedback" in old.columns:
        feedback_source = old[
            old["Feedback"].notna()
            & (old["Feedback"] != "")
            & (old["Feedback"] != "Pending")
        ]
        feedback_map = (
            feedback_source
            .drop_duplicates(subset=["Profile Key", "Role"], keep="last")
            .set_index(["Profile Key", "Role"])["Feedback"]
            .to_dict()
        )

        if "Feedback" not in to_save.columns:
            to_save["Feedback"] = ""
        to_save["Feedback"] = to_save.apply(
            lambda row: feedback_map.get(
                (row["Profile Key"], row["Role"]),
                row.get("Feedback", ""),
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
    combined = _clean_phone_column(combined)
    if "Profile Key" in combined.columns:
        combined = combined.drop_duplicates(subset=["Profile Key", "Role"], keep="last")

    # Supabase writes temporarily disabled; always save locally
    if supabase:
        print(f"[save_history] Supabase present, skipping cloud write for user_key={user_key}")

    try:
        DATA_DIR.mkdir(exist_ok=True)
        path = history_path(user_key)
        print(f"[save_history] writing {path}")
        combined.to_excel(path, index=False)
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
            response = (
                supabase.table("candidate_history")
                .select("*")
                .eq("user_key", user_key)
                .execute()
            )
            all_records = response.data or []

            target_ids = []
            for record in all_records:
                data = record.get("data", {}) or {}
                stored_role = str(data.get("Role", "")).strip().lower()
                if stored_role == role.strip().lower():
                    target_ids.append(record["id"])

            if not target_ids:
                print(f"No records found for role: '{role}'")
                return

            for rid in target_ids:
                supabase.table("candidate_history").delete().eq("id", rid).execute()

            print(f"✅ Successfully deleted history for role: '{role}'")
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
    df = _clean_phone_column(df)

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
                .execute()
            )
            if response.data:
                df = pd.DataFrame(response.data)
                df = df.rename(
                    columns={
                        "role": "Role",
                        "jd_text": "JD Text",
                        "saved_at": "Saved At",
                        "tags": "Tags",
                    }
                )
                return df[["Role", "JD Text", "Saved At", "Tags"]]
            return pd.DataFrame(columns=["Role", "JD Text", "Saved At", "Tags"])
        except Exception as e:
            print(f"Supabase load_jd_library error: {e}")

    path = jd_library_path(user_key)
    if path.exists():
        print(f"[load_jd_library] reading {path}")
        return pd.read_excel(path)
    return pd.DataFrame(columns=["Role", "JD Text", "Saved At", "Tags"])


def save_jd(user_key: str, role: str, jd_text: str, tags: str = "") -> bool:
    if not jd_text.strip() or not role.strip():
        print("[save_jd] Missing role or JD text")
        return False

    print(f"[save_jd] user_key={user_key}, role={role}")
    path = jd_library_path(user_key)
    print(f"[save_jd] jd_library_path={path}")

    if supabase:
        print(f"[save_jd] Supabase present, skipping cloud write for user_key={user_key}")

    DATA_DIR.mkdir(exist_ok=True)
    existing = load_jd_library(user_key)
    new_entry = pd.DataFrame(
        [
            {
                "Role": role.strip(),
                "JD Text": jd_text.strip(),
                "Saved At": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Tags": tags.strip(),
            }
        ]
    )

    if not existing.empty and "Role" in existing.columns:
        existing = existing[
            existing["Role"].astype(str).str.lower().str.strip() != role.lower().strip()
        ]

    combined = pd.concat([existing, new_entry], ignore_index=True)
    try:
        print(f"[save_jd] writing {path}")
        combined.to_excel(path, index=False)
        print(f"✅ JD saved locally for user: {user_key}")
        return True
    except Exception as e:
        print(f"❌ Local JD save failed: {e}")
        return False


def delete_jd(user_key: str, role: str) -> None:
    if supabase:
        try:
            supabase.table("jd_library").delete().eq("user_key", user_key).ilike("role", role.strip()).execute()
            print(f"✅ Deleted JD (cloud): {role}")
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
    print(f"✅ Deleted JD (local): {role}")


def get_jd(user_key: str, role: str) -> str:
    df = load_jd_library(user_key)
    if df.empty or "Role" not in df.columns:
        return ""
    match = df[df["Role"].astype(str).str.lower().str.strip() == role.lower().strip()]
    if match.empty:
        return ""
    return str(match.iloc[-1].get("JD Text", ""))


def update_feedback(user_key: str, profile_key_value: str, role: str, feedback: str) -> bool:
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

import pandas as pd
from .constants import DATA_DIR
from .parser import profile_key
from .utils import safe_filename_part


def history_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"candidate_history_{safe_filename_part(user_key)}.xlsx"


def legacy_history_path(user_key: str):
    return DATA_DIR / f"history_{safe_filename_part(user_key)}.csv"


def jd_library_path(user_key: str):
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"jd_library_{safe_filename_part(user_key)}.xlsx"


# ─── Candidate History ────────────────────────────────────────────────────────

def load_history(user_key: str) -> pd.DataFrame:
    path = history_path(user_key)
    if path.exists():
        return pd.read_excel(path)
    legacy = legacy_history_path(user_key)
    if legacy.exists():
        return pd.read_csv(legacy)
    return pd.DataFrame()


def save_history(df: pd.DataFrame, role: str, user_key: str, jd_text: str = "") -> None:
    if df.empty:
        return
    DATA_DIR.mkdir(exist_ok=True)
    old = load_history(user_key)
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
    combined.to_excel(history_path(user_key), index=False)


def clear_history(user_key: str) -> None:
    for path in [history_path(user_key), legacy_history_path(user_key)]:
        if path.exists():
            path.unlink()


def clear_role_history(user_key: str, role: str) -> None:
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


# ─── JD Library ───────────────────────────────────────────────────────────────

def load_jd_library(user_key: str) -> pd.DataFrame:
    path = jd_library_path(user_key)
    if path.exists():
        return pd.read_excel(path)
    return pd.DataFrame(columns=["Role", "JD Text", "Saved At", "Tags"])


def save_jd(user_key: str, role: str, jd_text: str, tags: str = "") -> bool:
    """Save a JD to the library. Returns True on success."""
    if not jd_text.strip() or not role.strip():
        return False
    DATA_DIR.mkdir(exist_ok=True)
    existing = load_jd_library(user_key)
    new_entry = pd.DataFrame([{
        "Role": role.strip(),
        "JD Text": jd_text.strip(),
        "Saved At": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Tags": tags.strip(),
    }])
    # overwrite if same role already saved
    if not existing.empty and "Role" in existing.columns:
        existing = existing[existing["Role"].astype(str).str.lower().str.strip() != role.lower().strip()]
    combined = pd.concat([existing, new_entry], ignore_index=True)
    combined.to_excel(jd_library_path(user_key), index=False)
    return True


def delete_jd(user_key: str, role: str) -> None:
    path = jd_library_path(user_key)
    if not path.exists():
        return
    df = pd.read_excel(path)
    if "Role" not in df.columns:
        return
    df = df[df["Role"].astype(str).str.lower().str.strip() != role.lower().strip()]
    df.to_excel(path, index=False)


def get_jd(user_key: str, role: str) -> str:
    """Retrieve JD text for a given role. Returns empty string if not found."""
    df = load_jd_library(user_key)
    if df.empty or "Role" not in df.columns:
        return ""
    match = df[df["Role"].astype(str).str.lower().str.strip() == role.lower().strip()]
    if match.empty:
        return ""
    return str(match.iloc[-1].get("JD Text", ""))

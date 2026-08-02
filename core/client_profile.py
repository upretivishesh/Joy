from datetime import datetime, timezone
from typing import Any, Dict

try:
    import streamlit as st
except ImportError:
    st = None


def _safe_strip(value: str) -> str:
    return (value or "").strip()


def _normalize_client_company(value: str) -> str:
    return " ".join(_safe_strip(value).split())


def get_supabase_client():
    """Get Supabase client safely."""
    try:
        from supabase import create_client
    except Exception:
        return None

    url = ""
    key = ""

    try:
        import os
        url = os.getenv("SUPABASE_URL") or ""
        key = os.getenv("SUPABASE_KEY") or ""
    except Exception:
        pass

    if (not url or not key) and st is not None:
        try:
            url = url or st.secrets.get("SUPABASE_URL") or ""
            key = key or st.secrets.get("SUPABASE_KEY") or ""
        except Exception:
            pass

    if not url or not key:
        return None

    try:
        return create_client(url, key)
    except Exception:
        return None


def get_default_profile() -> Dict[str, Any]:
    return {
        "preferred_industries": [],
        "language_preferences": [],
        "preferred_colleges": "",
        "min_experience": 0,
        "max_experience": 15,
        "culture_notes": "",
        "last_updated": "",
    }


def _coerce_profile_row(row: Dict[str, Any] | None) -> Dict[str, Any]:
    if not row:
        return get_default_profile()

    return {
        "preferred_industries": row.get("preferred_industries", []) or [],
        "language_preferences": row.get("language_preferences", []) or [],
        "preferred_colleges": row.get("preferred_colleges", "") or "",
        "min_experience": float(row.get("min_experience", 0) or 0),
        "max_experience": float(row.get("max_experience", 15) or 15),
        "culture_notes": row.get("culture_notes", "") or "",
        "last_updated": row.get("last_updated", "") or "",
    }


def list_client_companies(user_key: str) -> list[str]:
    """
    Return saved client company names, most recent first.
    Quietly returns [] if Supabase is unavailable.
    """
    user_key = _safe_strip(user_key)
    if not user_key:
        return []

    supabase = get_supabase_client()
    if not supabase:
        return []

    try:
        response = (
            supabase.table("client_personas")
            .select("client_company,last_updated")
            .eq("user_key", user_key)
            .order("last_updated", desc=True)
            .execute()
        )

        names: list[str] = []
        seen: set[str] = set()

        for row in response.data or []:
            name = _normalize_client_company(row.get("client_company", ""))
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)

        return names
    except Exception:
        return []


def load_client_profile(user_key: str, client_company: str) -> Dict[str, Any]:
    """Load persona from Supabase. Returns default dict if not found or unavailable."""
    user_key = _safe_strip(user_key)
    client_company = _normalize_client_company(client_company)

    if not user_key or not client_company:
        return get_default_profile()

    supabase = get_supabase_client()
    if not supabase:
        return get_default_profile()

    try:
        response = (
            supabase.table("client_personas")
            .select("*")
            .eq("user_key", user_key)
            .eq("client_company", client_company)
            .maybe_single()
            .execute()
        )
        return _coerce_profile_row(response.data)
    except Exception:
        return get_default_profile()


def save_client_profile(user_key: str, client_company: str, profile: Dict[str, Any]) -> bool:
    """Upsert persona into Supabase."""
    user_key = _safe_strip(user_key)
    client_company = _normalize_client_company(client_company)

    if not user_key or not client_company:
        return False

    supabase = get_supabase_client()
    if not supabase:
        return False

    try:
        data = {
            "user_key": user_key,
            "client_company": client_company,
            "preferred_industries": [str(x).strip() for x in (profile.get("preferred_industries") or []) if str(x).strip()],
            "language_preferences": [str(x).strip() for x in (profile.get("language_preferences") or []) if str(x).strip()],
            "preferred_colleges": _safe_strip(profile.get("preferred_colleges", "")),
            "min_experience": float(profile.get("min_experience", 0) or 0),
            "max_experience": float(profile.get("max_experience", 15) or 15),
            "culture_notes": _safe_strip(profile.get("culture_notes", "")),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        supabase.table("client_personas").upsert(
            data,
            on_conflict="user_key,client_company",
        ).execute()

        verify = (
            supabase.table("client_personas")
            .select("*")
            .eq("user_key", user_key)
            .eq("client_company", client_company)
            .maybe_single()
            .execute()
        )

        return bool(verify.data)
    except Exception:
        return False

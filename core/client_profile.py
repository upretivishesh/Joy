import os
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import streamlit as st
except ImportError:
    st = None

from supabase import create_client, Client


def get_supabase_client() -> Optional[Client]:
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
            if st is not None:
                st.warning(f"Supabase connection failed: {e}")
            return None
    return None


def list_client_companies(user_key: str) -> list[str]:
    """
    Names of every client this user already has a saved persona for,
    most-recently-updated first. Powers the 'pick from history' dropdown
    so Vishesh can select Atomgrid/Eunoia/Perch/etc. in one click instead
    of retyping the name.
    Returns [] quietly if Supabase isn't reachable.
    """
    supabase = get_supabase_client()
    if not supabase:
        return []

    try:
        response = (
            supabase.table("client_personas")
            .select("client_company, last_updated")
            .eq("user_key", user_key)
            .order("last_updated", desc=True)
            .execute()
        )
        names: list[str] = []
        for row in response.data or []:
            name = (row.get("client_company") or "").strip()
            if name and name not in names:
                names.append(name)
        return names
    except Exception as e:
        if st is not None:
            st.warning(f"Could not load client companies: {e}")
        return []


def get_default_profile() -> Dict[str, Any]:
    """Returns default empty persona profile."""
    return {
        "preferred_industries": [],
        "language_preferences": [],
        "preferred_colleges": "",
        "min_experience": 0,
        "max_experience": 15,
        "culture_notes": "",
        "last_updated": "",
    }


def load_client_profile(user_key: str, client_company: str) -> Dict[str, Any]:
    """Load persona from Supabase. Returns default dict if not found."""
    if not client_company or not client_company.strip():
        return get_default_profile()

    supabase = get_supabase_client()
    if not supabase:
        if st is not None:
            st.warning("Supabase not configured. Persona will not persist.")
        return get_default_profile()

    try:
        response = (
            supabase.table("client_personas")
            .select("*")
            .eq("user_key", user_key)
            .eq("client_company", client_company.strip())
            .limit(1)
            .execute()
        )

        if response.data:
            row = response.data[0]
            return {
                "preferred_industries": row.get("preferred_industries", []) or [],
                "language_preferences": row.get("language_preferences", []) or [],
                "preferred_colleges": row.get("preferred_colleges", "") or "",
                "min_experience": int(row.get("min_experience", 0) or 0),
                "max_experience": int(row.get("max_experience", 15) or 15),
                "culture_notes": row.get("culture_notes", "") or "",
                "last_updated": row.get("last_updated", "") or "",
            }
    except Exception as e:
        if st is not None:
            st.warning(f"Could not load client persona: {e}")

    return get_default_profile()


def save_client_profile(user_key: str, client_company: str, profile: Dict[str, Any]) -> bool:
    """Upsert persona into Supabase."""
    if not user_key or not str(user_key).strip():
        if st is not None:
            st.error("Missing user key. Please sign in again.")
        return False

    client_company = (client_company or "").strip()
    if not client_company:
        if st is not None:
            st.error("Client company name is required.")
        return False

    supabase = get_supabase_client()
    if not supabase:
        if st is not None:
            st.error("Supabase is not configured. Add SUPABASE_URL and SUPABASE_KEY in secrets.")
        return False

    try:
        data = {
            "user_key": str(user_key).strip(),
            "client_company": client_company,
            "preferred_industries": [str(x).strip() for x in profile.get("preferred_industries", []) if str(x).strip()],
            "language_preferences": [str(x).strip() for x in profile.get("language_preferences", []) if str(x).strip()],
            "preferred_colleges": str(profile.get("preferred_colleges", "") or "").strip(),
            "min_experience": int(profile.get("min_experience", 0) or 0),
            "max_experience": int(profile.get("max_experience", 15) or 15),
            "culture_notes": str(profile.get("culture_notes", "") or "").strip(),
            "last_updated": datetime.now().isoformat(),
        }

        if data["max_experience"] < data["min_experience"]:
            data["max_experience"] = data["min_experience"]

        response = (
            supabase.table("client_personas")
            .upsert(data, on_conflict="user_key,client_company")
            .execute()
        )

        if getattr(response, "data", None) is None:
            if st is not None:
                st.warning("Persona save returned no data. Please verify Supabase table schema and RLS.")
        return True

    except Exception as e:
        if st is not None:
            st.error(f"Failed to save client persona: {e}")
        return False

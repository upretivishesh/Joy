from datetime import datetime
from typing import Dict, Any

import streamlit as st


def get_supabase_client():
    """Get Supabase client - matches your existing history.py pattern"""
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL") or ""
        key = st.secrets.get("SUPABASE_KEY") or ""
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
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
    except Exception:
        return []


def get_default_profile() -> Dict[str, Any]:
    """Returns default empty persona profile"""
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
                "min_experience": row.get("min_experience", 0) or 0,
                "max_experience": row.get("max_experience", 15) or 15,
                "culture_notes": row.get("culture_notes", "") or "",
                "last_updated": row.get("last_updated", "") or "",
            }
    except Exception as e:
        st.warning(f"Could not load client persona: {e}")

    return get_default_profile()


def save_client_profile(user_key: str, client_company: str, profile: Dict[str, Any]) -> bool:
    """Upsert persona into Supabase"""
    if not client_company or not client_company.strip():
        return False

    supabase = get_supabase_client()
    if not supabase:
        return False

    try:
        data = {
            "user_key": user_key,
            "client_company": client_company.strip(),
            "preferred_industries": profile.get("preferred_industries", []),
            "language_preferences": profile.get("language_preferences", []),
            "preferred_colleges": profile.get("preferred_colleges", ""),
            "min_experience": profile.get("min_experience", 0),
            "max_experience": profile.get("max_experience", 15),
            "culture_notes": profile.get("culture_notes", ""),
            "last_updated": datetime.now().isoformat(),
        }

        supabase.table("client_personas").upsert(
            data,
            on_conflict="user_key,client_company"
        ).execute()
        return True
    except Exception as e:
        st.error(f"Failed to save client persona: {e}")
        return False

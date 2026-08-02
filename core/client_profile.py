from datetime import datetime
from typing import Dict, Any
import os

import streamlit as st


def get_supabase_client():
    """Safely get Supabase client."""
    try:
        from supabase import create_client
    except Exception:
        return None

    url = os.getenv("SUPABASE_URL") or ""
    key = os.getenv("SUPABASE_KEY") or ""

    if (not url or not key):
        try:
            url = url or st.secrets.get("SUPABASE_URL") or ""
            key = key or st.secrets.get("SUPABASE_KEY") or ""
        except Exception:
            pass

    if not url or not key:
        return None

    try:
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase connection failed: {e}")
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


def _clean_company_name(value: str) -> str:
    return " ".join((value or "").strip().split())


def list_client_companies(user_key: str) -> list[str]:
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
        seen: set[str] = set()

        for row in response.data or []:
            name = _clean_company_name(row.get("client_company", ""))
            key = name.lower()
            if name and key not in seen:
                seen.add(key)
                names.append(name)

        return names
    except Exception as e:
        st.warning(f"Could not list client personas: {e}")
        return []


def load_client_profile(user_key: str, client_company: str) -> Dict[str, Any]:
    client_company = _clean_company_name(client_company)
    if not client_company:
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
    client_company = _clean_company_name(client_company)
    if not client_company:
        st.error("Client name is blank.")
        return False

    supabase = get_supabase_client()
    if not supabase:
        st.error("Supabase client not available.")
        return False

    try:
        data = {
            "user_key": user_key,
            "client_company": client_company,
            "preferred_industries": [str(x).strip() for x in (profile.get("preferred_industries", []) or []) if str(x).strip()],
            "language_preferences": [str(x).strip() for x in (profile.get("language_preferences", []) or []) if str(x).strip()],
            "preferred_colleges": str(profile.get("preferred_colleges", "") or "").strip(),
            "min_experience": int(profile.get("min_experience", 0) or 0),
            "max_experience": int(profile.get("max_experience", 15) or 15),
            "culture_notes": str(profile.get("culture_notes", "") or "").strip(),
            "last_updated": datetime.now().isoformat(),
        }

        supabase.table("client_personas").upsert(
            data,
            on_conflict="user_key,client_company"
        ).execute()

        verify = (
            supabase.table("client_personas")
            .select("client_company")
            .eq("user_key", user_key)
            .eq("client_company", client_company)
            .limit(1)
            .execute()
        )

        return bool(verify.data)
    except Exception as e:
        st.error(f"Failed to save client persona: {e}")
        return False

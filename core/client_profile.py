# core/client_profile.py
from datetime import datetime
from typing import Optional, Dict, Any, List
import json
import os

import streamlit as st

from .constants import DATA_DIR
from .utils import safe_filename_part


def get_supabase_client():
    """Get Supabase client safely, matching history.py behavior."""
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
        print(f"Supabase connection failed for client_personas: {e}")
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


def _persona_dir():
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "personas"
    path.mkdir(exist_ok=True)
    return path


def _persona_path(user_key: str, client_company: str):
    safe_user = safe_filename_part(user_key or "local")
    safe_company = safe_filename_part(_clean_company_name(client_company) or "default")
    return _persona_dir() / f"{safe_user}__{safe_company}.json"


def _save_local_persona(user_key: str, client_company: str, profile: Dict[str, Any]) -> bool:
    try:
        path = _persona_path(user_key, client_company)
        payload = {
            "user_key": user_key,
            "client_company": _clean_company_name(client_company),
            "preferred_industries": profile.get("preferred_industries", []) or [],
            "language_preferences": profile.get("language_preferences", []) or [],
            "preferred_colleges": profile.get("preferred_colleges", "") or "",
            "min_experience": int(profile.get("min_experience", 0) or 0),
            "max_experience": int(profile.get("max_experience", 15) or 15),
            "culture_notes": profile.get("culture_notes", "") or "",
            "last_updated": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"Local persona save failed: {e}")
        return False


def _load_local_persona(user_key: str, client_company: str) -> Dict[str, Any]:
    try:
        path = _persona_path(user_key, client_company)
        if not path.exists():
            return get_default_profile()

        row = json.loads(path.read_text(encoding="utf-8"))
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
        print(f"Local persona load failed: {e}")
        return get_default_profile()


def list_client_companies(user_key: str) -> List[str]:
    names = []
    seen = set()

    supabase = get_supabase_client()
    if supabase:
        try:
            response = (
                supabase.table("client_personas")
                .select("client_company, last_updated")
                .eq("user_key", user_key)
                .order("last_updated", desc=True)
                .execute()
            )

            for row in response.data or []:
                name = _clean_company_name(row.get("client_company", ""))
                lowered = name.lower()
                if name and lowered not in seen:
                    seen.add(lowered)
                    names.append(name)
        except Exception as e:
            print(f"Supabase list_client_companies failed: {e}")

    try:
        persona_dir = _persona_dir()
        safe_user = safe_filename_part(user_key or "local")
        prefix = f"{safe_user}__"
        local_files = sorted(persona_dir.glob(f"{prefix}*.json"), reverse=True)

        for path in local_files:
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                name = _clean_company_name(row.get("client_company", ""))
                lowered = name.lower()
                if name and lowered not in seen:
                    seen.add(lowered)
                    names.append(name)
            except Exception:
                pass
    except Exception as e:
        print(f"Local list_client_companies failed: {e}")

    return names


def load_client_profile(user_key: str, client_company: str) -> Dict[str, Any]:
    client_company = _clean_company_name(client_company)
    if not client_company:
        return get_default_profile()

    supabase = get_supabase_client()
    if supabase:
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
                profile = {
                    "preferred_industries": row.get("preferred_industries", []) or [],
                    "language_preferences": row.get("language_preferences", []) or [],
                    "preferred_colleges": row.get("preferred_colleges", "") or "",
                    "min_experience": row.get("min_experience", 0) or 0,
                    "max_experience": row.get("max_experience", 15) or 15,
                    "culture_notes": row.get("culture_notes", "") or "",
                    "last_updated": row.get("last_updated", "") or "",
                }
                _save_local_persona(user_key, client_company, profile)
                return profile
        except Exception as e:
            print(f"Supabase load_client_profile failed: {e}")

    return _load_local_persona(user_key, client_company)


def save_client_profile(user_key: str, client_company: str, profile: Dict[str, Any]) -> bool:
    client_company = _clean_company_name(client_company)
    if not client_company:
        st.error("Client name is blank.")
        return False

    data = {
        "user_key": user_key,
        "client_company": client_company,
        "preferred_industries": profile.get("preferred_industries", []) or [],
        "language_preferences": profile.get("language_preferences", []) or [],
        "preferred_colleges": profile.get("preferred_colleges", "") or "",
        "min_experience": int(profile.get("min_experience", 0) or 0),
        "max_experience": int(profile.get("max_experience", 15) or 15),
        "culture_notes": profile.get("culture_notes", "") or "",
        "last_updated": datetime.now().isoformat(),
    }

    local_saved = _save_local_persona(user_key, client_company, data)

    supabase = get_supabase_client()
    if not supabase:
        if local_saved:
            st.warning("Saved persona locally. Supabase is not configured.")
            return True
        st.error("Supabase unavailable and local persona backup failed.")
        return False

    try:
        supabase.table("client_personas").upsert(
            data,
            on_conflict="user_key,client_company"
        ).execute()

        if local_saved:
            st.success("Persona saved successfully.")
        else:
            st.warning("Persona saved to Supabase, but local backup failed.")
        return True

    except Exception as e:
        if local_saved:
            st.warning(f"Saved persona locally because Supabase save failed: {e}")
            return True

        st.error(f"Failed to save client persona: {e}")
        return False

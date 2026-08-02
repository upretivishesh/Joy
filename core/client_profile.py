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

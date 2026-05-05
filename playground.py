import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Joy | AI Recruiter",
    page_icon="✦",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────
defaults = {
    "authenticated": True,   # keep True for now (skip login while testing)
    "name": "Vishesh",
    "page": "home",
    "chat_history": [],
    "results": None,
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────
# NAVIGATION (SMART + CONTROLLED RERUN)
# ─────────────────────────────────────────────────────────────────
def go(page_name):
    if st.session_state.page != page_name:
        st.session_state.page = page_name
        st.rerun()

def render_nav():
    page = st.session_state.page
    cols = st.columns(4)

    nav_items = ["home", "screen", "outreach", "history"]

    for i, p in enumerate(nav_items):
        label = p.capitalize()

        # subtle active state
        if page == p:
            label = f"● {label}"

        if cols[i].button(label, use_container_width=True):
            go(p)

# ─────────────────────────────────────────────────────────────────
# GLOBAL NAV
# ─────────────────────────────────────────────────────────────────
render_nav()

# ✅ FIX: ALWAYS DEFINE PAGE AFTER NAV
page = st.session_state.page

# ─────────────────────────────────────────────────────────────────
# HOME
# ─────────────────────────────────────────────────────────────────
if page == "home":

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    first = st.session_state.name.split()[0]

    st.title(f"Hey {first}")
    st.caption("Joy is ready. Let's hire someone dangerous.")

    msg = st.text_input("Ask Joy", placeholder="Try: screen candidates / outreach / anything")

    if msg:
        st.session_state.chat_history.append(msg)

        msg_lower = msg.lower()

        if "screen" in msg_lower:
            go("screen")

        elif "outreach" in msg_lower:
            go("outreach")

        else:
            with st.spinner("Thinking..."):
                st.write(f"You said: {msg}")

# ─────────────────────────────────────────────────────────────────
# SCREEN
# ─────────────────────────────────────────────────────────────────
elif page == "screen":

    st.title("Screen Resumes")

    uploaded = st.file_uploader("Upload resumes", accept_multiple_files=True)

    if uploaded:
        st.success(f"{len(uploaded)} resumes uploaded")

        if st.button("Run Screening"):
            with st.spinner("Screening..."):
                # mock results
                st.session_state.results = [
                    {"name": "Candidate A", "score": 87},
                    {"name": "Candidate B", "score": 78},
                    {"name": "Candidate C", "score": 91},
                ]

    if st.session_state.results:
        st.subheader("Results")

        for r in st.session_state.results:
            st.write(f"{r['name']} — {r['score']}")

        if st.button("Go to Outreach"):
            go("outreach")

# ─────────────────────────────────────────────────────────────────
# OUTREACH
# ─────────────────────────────────────────────────────────────────
elif page == "outreach":

    st.title("Outreach")

    if not st.session_state.results:
        st.warning("No candidates yet.")

        if st.button("Go to Screen"):
            go("screen")

    else:
        st.subheader("Contact Candidates")

        for r in st.session_state.results:
            st.write(f"📬 Emailing {r['name']}...")

# ─────────────────────────────────────────────────────────────────
# HISTORY
# ─────────────────────────────────────────────────────────────────
elif page == "history":

    st.title("History")

    if st.session_state.results:
        st.write("Past candidates:")

        for r in st.session_state.results:
            st.write(r)

    else:
        st.info("No history yet.")

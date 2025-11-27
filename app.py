import streamlit as st
from joy_core import process_resumes_with_jd

st.set_page_config(page_title="Joy – Seven Hiring", layout="wide")

st.title("Joy – Seven Hiring")

st.markdown("### Role configuration")
role = st.text_input("Role title", value="Assistant Manager – Logistics")

st.markdown(
    "Upload a Job Description (JD) and one or more resumes. "
    "Joy will extract basic details, screen them against the JD, "
    "and generate WhatsApp messages for outreach."
)

st.markdown("### Uploads")

jd_file = st.file_uploader(
    "Upload JD (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"], key="jd_uploader"
)

resume_files = st.file_uploader(
    "Upload Resumes (PDF or DOCX)",
    type=["pdf", "docx"],
    accept_multiple_files=True,
    key="resumes_uploader",
)

run_button = st.button("Run screening

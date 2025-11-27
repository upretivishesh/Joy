import streamlit as st
from joy_core import process_resumes_with_jd

st.set_page_config(page_title="Joy – Seven Hiring", layout="wide")

st.title("Joy – Seven Hiring")

st.markdown("### Role configuration")
role = st.text_input("Role title", value="")

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

run_button = st.button("Run screening")

if run_button:
    if not jd_file:
        st.error("Please upload a JD file.")
    elif not resume_files:
        st.error("Please upload at least one resume.")
    else:
        with st.spinner("Screening resumes..."):
            df, excel_bytes = process_resumes_with_jd(
                jd_file,
                resume_files,
                role=role,
            )

        if df.empty:
            st.warning("No data extracted from the uploaded resumes.")
        else:
            st.success("Screening complete.")
            st.subheader("Results")
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.download_button(
                label="Download Excel file",
                data=excel_bytes,
                file_name="candidates_details.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

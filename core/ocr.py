import threading
from io import BytesIO

import streamlit as st

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from docx import Document
except Exception:
    Document = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from pdf2image import convert_from_bytes
except Exception:
    convert_from_bytes = None


ocr_lock = threading.Lock()

if pytesseract is not None:
    default_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    try:
        pytesseract.pytesseract.tesseract_cmd = default_tesseract
    except Exception:
        pass


def ocr_pdf(data: bytes) -> str:
    if pytesseract is None or convert_from_bytes is None:
        return ""
    try:
        images = convert_from_bytes(data, dpi=180, first_page=1, last_page=5)
        text_parts = []
        for image in images:
            text_parts.append(pytesseract.image_to_string(image))
        return "\n".join(text_parts).strip()
    except Exception:
        return ""


@st.cache_data(show_spinner=False, max_entries=250)
def read_uploaded_file(file_name: str, data: bytes) -> tuple[str, str]:
    name = file_name.lower()
    try:
        if name.endswith(".pdf"):
            if pdfplumber is None:
                return "", "pdfplumber is not installed."
            with pdfplumber.open(BytesIO(data)) as pdf:
                pages = pdf.pages[:8]
                text = "\n".join(page.extract_text() or "" for page in pages).strip()

            alpha_ratio = sum(c.isalpha() for c in text) / max(len(text), 1)
            if alpha_ratio < 0.25:
                with ocr_lock:
                    ocr_text = ocr_pdf(data)
                if len(ocr_text) > len(text):
                    text = ocr_text
            return text.strip(), ""

        if name.endswith(".docx"):
            if Document is None:
                return "", "python-docx is not installed."
            doc = Document(BytesIO(data))
            text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_text = " ".join(cell.text for cell in row.cells if cell.text.strip())
                    if row_text:
                        text_parts.append(row_text)
            text = "\n".join(text_parts).strip()
            if not text:
                return "", "DOCX opened but no readable text found."
            return text, ""

        if name.endswith(".txt"):
            return data.decode("utf-8", errors="ignore").strip(), ""

        return "", "Unsupported file type."
    except Exception as exc:
        return "", f"Could not read file: {exc}"

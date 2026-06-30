import os
from typing import List, Dict, Optional
from pathlib import Path

from .parser import (
    extract_jd_requirements_ai,
    parse_min_experience,
    detect_role_title,
    extract_keywords_from_jd,
)
from .llm_extractor import extract_keywords_llm
from .scoring import score_resume
from .semantic import semantic_similarity_score


def process_jd_and_resumes(
    jd_text: str,
    resume_files: List[str],           # List of resume file paths
    api_key: str,
    model: str = "gpt-4o-mini",
    output_dir: Optional[str] = None,
    use_llm_keywords: bool = True,
    use_semantic: bool = True,
) -> List[Dict]:
    """
    Main pipeline: Process one JD against multiple resumes.
    Returns list of scoring results sorted by Final Score (descending).
    """

    if not jd_text or not resume_files:
        return []

    print(f"\n[Pipeline] Processing JD against {len(resume_files)} resumes...")

    # === 1. Extract structured info from JD ===
    jd_requirements = extract_jd_requirements_ai(jd_text, api_key, model) if api_key else {}
    role = detect_role_title(jd_text, "", api_key, model) or "Open Role"
    min_exp = parse_min_experience(jd_text)

    # === 2. Get best keywords (LLM preferred) ===
    keywords = []
    if use_llm_keywords and api_key:
        keywords = extract_keywords_llm(jd_text, api_key, model)
        print(f"[Pipeline] LLM extracted {len(keywords)} keywords")

    if not keywords:
        # Fallback to traditional extraction + cleaning
        keywords = extract_keywords_from_jd(jd_text, limit=30)
        print(f"[Pipeline] Using fallback keywords: {len(keywords)}")

    results = []

    # === 3. Score each resume ===
    for idx, resume_path in enumerate(resume_files, 1):
        filename = os.path.basename(resume_path)
        print(f"[{idx}/{len(resume_files)}] Scoring: {filename}")

        try:
            with open(resume_path, "r", encoding="utf-8", errors="ignore") as f:
                resume_text = f.read()

            result = score_resume(
                jd_text=jd_text,
                role=role,
                resume_text=resume_text,
                filename=filename,
                keywords=keywords,
                min_exp=min_exp,
                api_key=api_key,
                model=model,
                jd_requirements=jd_requirements,
                use_semantic=use_semantic,
                use_llm_keywords=False,   # Already extracted above
            )

            # Add extra useful fields
            result["Resume File"] = filename
            result["Role"] = role

            results.append(result)

        except Exception as e:
            print(f"  Error processing {filename}: {e}")
            results.append({
                "Resume File": filename,
                "Final Score": 0,
                "Verdict": "Error",
                "Reason": str(e),
            })

    # === 4. Sort by Final Score (highest first) ===
    results.sort(key=lambda x: x.get("Final Score", 0), reverse=True)

    print(f"\n[Pipeline] Completed. Top score: {results[0]['Final Score'] if results else 0}")

    # Optional: Save results
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        # You can add export logic here (CSV/Excel) using your exports.py

    return results


def run_pipeline_from_folder(
    jd_path: str,
    resumes_folder: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    output_dir: Optional[str] = "output",
) -> List[Dict]:
    """
    Convenience function: Run pipeline using file paths.
    """
    # Load JD
    with open(jd_path, "r", encoding="utf-8", errors="ignore") as f:
        jd_text = f.read()

    # Get all resume files
    resume_files = [
        str(p) for p in Path(resumes_folder).glob("*")
        if p.suffix.lower() in [".pdf", ".docx", ".doc", ".txt"]
    ]

    if not resume_files:
        print("No resume files found!")
        return []

    return process_jd_and_resumes(
        jd_text=jd_text,
        resume_files=resume_files,
        api_key=api_key,
        model=model,
        output_dir=output_dir,
    )


# Example usage (for testing in VS Code)
if __name__ == "__main__":
    # Example - replace with your actual paths and key
    API_KEY = "sk-your-openai-key-here"

    jd_file = "data/sample_jd.txt"
    resumes_dir = "data/resumes"

    results = run_pipeline_from_folder(
        jd_path=jd_file,
        resumes_folder=resumes_dir,
        api_key=API_KEY,
        model="gpt-4o-mini",
        output_dir="output"
    )

    for r in results[:5]:  # Show top 5
        print(f"{r['Final Score']:5.1f} | {r['Verdict']:12} | {r['Resume File']}")

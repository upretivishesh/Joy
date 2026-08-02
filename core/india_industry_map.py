# core/india_industry_map.py
import re

INDIA_INDUSTRY_KEYWORDS = [
    # Agrochemicals / crop inputs — keep BEFORE generic chemicals
    ("agrochemical", "Agrochemicals"),
    ("agrochemicals", "Agrochemicals"),
    ("crop protection", "Agrochemicals"),
    ("crop care", "Agrochemicals"),
    ("pesticide", "Agrochemicals"),
    ("pesticides", "Agrochemicals"),
    ("insecticide", "Agrochemicals"),
    ("insecticides", "Agrochemicals"),
    ("fungicide", "Agrochemicals"),
    ("fungicides", "Agrochemicals"),
    ("herbicide", "Agrochemicals"),
    ("herbicides", "Agrochemicals"),
    ("plant nutrition", "Agrochemicals"),
    ("bio stimulant", "Agrochemicals"),
    ("biostimulant", "Agrochemicals"),
    ("bio fertilizer", "Agrochemicals"),
    ("fertilizer", "Agrochemicals"),
    ("fertilisers", "Agrochemicals"),
    ("fertilizers", "Agrochemicals"),
    ("seeds", "Agriculture / Agritech"),
    ("seed company", "Agriculture / Agritech"),
    ("agri input", "Agrochemicals"),
    ("agri inputs", "Agrochemicals"),

    # Major companies / brands
    ("tata motors", "Automotive"),
    ("mahindra", "Automotive"),
    ("maruti", "Automotive"),
    ("hero", "Automotive"),
    ("tvs", "Automotive"),
    ("hul", "FMCG"),
    ("itc", "FMCG"),
    ("dabur", "FMCG"),
    ("nestle", "FMCG"),
    ("reliance retail", "Retail"),
    ("dmart", "Retail"),
    ("zepto", "Retail"),
    ("blinkit", "Retail"),
    ("sun pharma", "Pharmaceuticals"),
    ("cipla", "Pharmaceuticals"),
    ("dr reddy", "Pharmaceuticals"),
    ("lupin", "Pharmaceuticals"),
    ("tata steel", "Steel / Metals"),
    ("jsw steel", "Steel / Metals"),
    ("hindalco", "Metals"),
    ("adani", "Energy / Infrastructure"),
    ("iocl", "Oil & Gas"),
    ("ongc", "Oil & Gas"),
    ("bpcl", "Oil & Gas"),
    ("hpcl", "Oil & Gas"),
    ("l&t", "Construction / Infrastructure"),
    ("grasim", "Chemicals / Cement"),
    ("pidilite", "Chemicals"),
    ("asian paints", "Paints / Chemicals"),

    # Common keywords
    ("automotive", "Automotive"),
    ("auto component", "Automotive"),
    ("fmcg", "FMCG"),
    ("pharma", "Pharmaceuticals"),
    ("pharmaceutical", "Pharmaceuticals"),
    ("steel", "Steel / Metals"),
    ("oil & gas", "Oil & Gas"),
    ("oil and gas", "Oil & Gas"),
    ("refinery", "Oil & Gas"),
    ("logistics", "Logistics"),
    ("supply chain", "Logistics"),
    ("construction", "Construction"),
    ("infrastructure", "Construction"),
    ("retail", "Retail"),
    ("agriculture", "Agriculture / Agritech"),
    ("agritech", "Agriculture / Agritech"),
    ("agri", "Agriculture / Agritech"),
    ("specialty chemical", "Chemicals"),
    ("speciality chemical", "Chemicals"),
    ("chemical", "Chemicals"),
    ("manufacturing", "Manufacturing"),
    ("production", "Manufacturing"),
    ("plant", "Manufacturing"),
    ("factory", "Manufacturing"),
]


def _normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def get_candidate_industry(resume_text: str, filename: str = "") -> str:
    if not resume_text:
        return "Others / Not Detected"

    text = _normalize_text(f"{resume_text} {filename}")

    for keyword, industry in INDIA_INDUSTRY_KEYWORDS:
        if _normalize_text(keyword) in text:
            return industry

    if any(word in text for word in ["factory", "plant", "unit", "production", "manufacturer", "manufacturing"]):
        return "Manufacturing"

    return "Others / Not Detected"

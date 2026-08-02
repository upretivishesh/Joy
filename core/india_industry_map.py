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
    ("bio fertilizers", "Agrochemicals"),
    ("fertilizer", "Agrochemicals"),
    ("fertiliser", "Agrochemicals"),
    ("fertilisers", "Agrochemicals"),
    ("fertilizers", "Agrochemicals"),
    ("agri input", "Agrochemicals"),
    ("agri inputs", "Agrochemicals"),

    # Agriculture / agritech
    ("seeds", "Agriculture / Agritech"),
    ("seed company", "Agriculture / Agritech"),
    ("agriculture", "Agriculture / Agritech"),
    ("agritech", "Agriculture / Agritech"),
    ("organic farming", "Agriculture / Agritech"),
    ("regenerative farming", "Agriculture / Agritech"),
    ("farm input", "Agriculture / Agritech"),
    ("farm inputs", "Agriculture / Agritech"),

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

    # Consumer / retail / D2C
    ("fmcg", "FMCG"),
    ("consumer goods", "FMCG"),
    ("food and beverage", "FMCG"),
    ("food beverage", "FMCG"),
    ("d2c", "D2C / Consumer Brands"),
    ("dtc", "D2C / Consumer Brands"),
    ("direct to consumer", "D2C / Consumer Brands"),
    ("consumer brand", "D2C / Consumer Brands"),
    ("consumer brands", "D2C / Consumer Brands"),
    ("e commerce", "E-commerce"),
    ("ecommerce", "E-commerce"),
    ("marketplace", "E-commerce"),
    ("retail", "Retail"),

    # Healthcare / life sciences
    ("pharma", "Pharmaceuticals"),
    ("pharmaceutical", "Pharmaceuticals"),
    ("pharmaceuticals", "Pharmaceuticals"),
    ("healthcare", "Healthcare"),
    ("hospital", "Healthcare"),
    ("biotech", "Biotechnology"),

    # Industrial / core sectors
    ("automotive", "Automotive"),
    ("auto component", "Automotive"),
    ("auto components", "Automotive"),
    ("steel", "Steel / Metals"),
    ("metals", "Steel / Metals"),
    ("oil and gas", "Oil & Gas"),
    ("oil gas", "Oil & Gas"),
    ("oil & gas", "Oil & Gas"),
    ("refinery", "Oil & Gas"),
    ("logistics", "Logistics"),
    ("supply chain", "Logistics"),
    ("warehouse", "Logistics"),
    ("warehousing", "Logistics"),
    ("construction", "Construction"),
    ("infrastructure", "Construction"),
    ("real estate", "Construction"),
    ("specialty chemical", "Chemicals"),
    ("specialty chemicals", "Chemicals"),
    ("speciality chemical", "Chemicals"),
    ("speciality chemicals", "Chemicals"),
    ("chemical", "Chemicals"),
    ("chemicals", "Chemicals"),
    ("paints", "Paints / Chemicals"),
    ("coatings", "Paints / Chemicals"),
    ("manufacturing", "Manufacturing"),
    ("production", "Manufacturing"),
    ("plant", "Manufacturing"),
    ("factory", "Manufacturing"),
]

MANUFACTURING_SIGNALS = [
    "factory",
    "plant",
    "unit",
    "production",
    "manufacturer",
    "manufacturing",
    "assembly line",
    "shop floor",
]


def _normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("&", " and ")
    value = value.replace("/", " ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def get_candidate_industry(resume_text: str, filename: str = "") -> str:
    """
    Returns a clean industry label for Indian non-IT / mixed-industry resumes.
    Used as a deterministic fallback when AI scoring does not provide a useful
    candidate industry label.
    """
    if not resume_text:
        return "Others / Not Detected"

    text = _normalize_text(f"{resume_text} {filename}")

    for keyword, industry in INDIA_INDUSTRY_KEYWORDS:
        if _normalize_text(keyword) in text:
            return industry

    if any(word in text for word in MANUFACTURING_SIGNALS):
        return "Manufacturing"

    return "Others / Not Detected"

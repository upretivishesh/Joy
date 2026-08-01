# core/india_industry_map.py

INDIA_INDUSTRY_MAP = {
    # Major Companies & Brands
    "tata motors": "Automotive",
    "mahindra": "Automotive",
    "maruti": "Automotive",
    "hero": "Automotive",
    "tvs": "Automotive",
    "hul": "FMCG",
    "itc": "FMCG",
    "dabur": "FMCG",
    "nestle": "FMCG",
    "reliance retail": "Retail",
    "dmart": "Retail",
    "zepto": "Retail",
    "blinkit": "Retail",
    "sun pharma": "Pharmaceuticals",
    "cipla": "Pharmaceuticals",
    "dr reddy": "Pharmaceuticals",
    "lupin": "Pharmaceuticals",
    "tata steel": "Steel / Metals",
    "jsw steel": "Steel / Metals",
    "hindalco": "Metals",
    "adani": "Energy / Infrastructure",
    "iocl": "Oil & Gas",
    "ongc": "Oil & Gas",
    "bpcl": "Oil & Gas",
    "hpcl": "Oil & Gas",
    "l&t": "Construction / Infrastructure",
    "grasim": "Chemicals / Cement",
    "pidilite": "Chemicals",
    "asian paints": "Paints / Chemicals",

    # Common Keywords
    "automotive": "Automotive",
    "auto component": "Automotive",
    "fmcg": "FMCG",
    "pharma": "Pharmaceuticals",
    "pharmaceutical": "Pharmaceuticals",
    "steel": "Steel / Metals",
    "oil & gas": "Oil & Gas",
    "oil and gas": "Oil & Gas",
    "refinery": "Oil & Gas",
    "logistics": "Logistics",
    "supply chain": "Logistics",
    "construction": "Construction",
    "infrastructure": "Construction",
    "retail": "Retail",
    "agri": "Agriculture / Agritech",
    "chemical": "Chemicals",
    "manufacturing": "Manufacturing",
    "production": "Manufacturing",
    "plant": "Manufacturing",
    "factory": "Manufacturing",
}


def get_candidate_industry(resume_text: str, filename: str = "") -> str:
    """
    Returns a clean industry label for Indian non-IT companies.
    Used as a strong fallback when AI returns N/A.
    """
    if not resume_text:
        return "Others / Not Detected"

    text = (resume_text + " " + filename).lower()

    for keyword, industry in INDIA_INDUSTRY_MAP.items():
        if keyword in text:
            return industry

    # Extra common manufacturing signals
    if any(word in text for word in ["factory", "plant", "unit", "production", "manufacturer", "manufacturing"]):
        return "Manufacturing"

    return "Others / Not Detected"

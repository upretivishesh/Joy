# core/india_industry_map.py

import re


INDIA_INDUSTRY_MAP = {
    # Automotive
    "tata motors": "Automotive",
    "mahindra": "Automotive",
    "maruti": "Automotive",
    "hero motocorp": "Automotive",
    "hero": "Automotive",
    "tvs": "Automotive",
    "bajaj auto": "Automotive",
    "ashok leyland": "Automotive",
    "automotive": "Automotive",
    "automobile": "Automotive",
    "auto component": "Automotive",
    "autocomponent": "Automotive",
    "vehicle": "Automotive",
    "oem": "Automotive",

    # FMCG / Consumer
    "hul": "FMCG",
    "hindustan unilever": "FMCG",
    "itc": "FMCG",
    "dabur": "FMCG",
    "nestle": "FMCG",
    "britannia": "FMCG",
    "marico": "FMCG",
    "gcpl": "FMCG",
    "godrej consumer": "FMCG",
    "fmcg": "FMCG",
    "consumer goods": "FMCG",
    "fast moving consumer goods": "FMCG",
    "personal care": "FMCG",
    "home care": "FMCG",
    "foods": "FMCG",
    "beverages": "FMCG",

    # Retail / D2C / Ecommerce
    "reliance retail": "Retail",
    "dmart": "Retail",
    "avenue supermarts": "Retail",
    "zepto": "Retail",
    "blinkit": "Retail",
    "bigbasket": "Retail",
    "flipkart": "Retail",
    "amazon": "Retail",
    "retail": "Retail",
    "modern trade": "Retail",
    "general trade": "Retail",
    "ecommerce": "Retail",
    "e commerce": "Retail",
    "d2c": "Retail",
    "direct to consumer": "Retail",

    # Pharmaceuticals / Healthcare
    "sun pharma": "Pharmaceuticals",
    "cipla": "Pharmaceuticals",
    "dr reddy": "Pharmaceuticals",
    "dr. reddy": "Pharmaceuticals",
    "lupin": "Pharmaceuticals",
    "torrent pharma": "Pharmaceuticals",
    "zydus": "Pharmaceuticals",
    "alkem": "Pharmaceuticals",
    "mankind": "Pharmaceuticals",
    "pharma": "Pharmaceuticals",
    "pharmaceutical": "Pharmaceuticals",
    "pharmaceuticals": "Pharmaceuticals",
    "formulation": "Pharmaceuticals",
    "api": "Pharmaceuticals",
    "healthcare": "Pharmaceuticals",

    # Chemicals / Agrochemicals / Paints
    "pidilite": "Chemicals",
    "asian paints": "Paints / Chemicals",
    "berger paints": "Paints / Chemicals",
    "kansai nerolac": "Paints / Chemicals",
    "akzonobel": "Paints / Chemicals",
    "basf": "Chemicals",
    "upl": "Agrochemicals",
    "coromandel": "Agrochemicals",
    "pi industries": "Agrochemicals",
    "sumitomo chemical": "Agrochemicals",
    "syngenta": "Agrochemicals",
    "bayer crop science": "Agrochemicals",
    "rallis": "Agrochemicals",
    "dhanuka": "Agrochemicals",
    "insecticide india": "Agrochemicals",
    "agrochemical": "Agrochemicals",
    "agro chemical": "Agrochemicals",
    "agrochemicals": "Agrochemicals",
    "crop protection": "Agrochemicals",
    "pesticide": "Agrochemicals",
    "herbicide": "Agrochemicals",
    "fungicide": "Agrochemicals",
    "fertilizer": "Agrochemicals",
    "fertiliser": "Agrochemicals",
    "speciality chemical": "Chemicals",
    "specialty chemical": "Chemicals",
    "chemical": "Chemicals",
    "chemicals": "Chemicals",
    "solvent": "Chemicals",
    "resin": "Chemicals",
    "paint": "Paints / Chemicals",
    "paints": "Paints / Chemicals",
    "coating": "Paints / Chemicals",
    "coatings": "Paints / Chemicals",

    # Agriculture / Seeds / Agritech
    "agri": "Agriculture / Agritech",
    "agriculture": "Agriculture / Agritech",
    "agricultural": "Agriculture / Agritech",
    "agritech": "Agriculture / Agritech",
    "farm input": "Agriculture / Agritech",
    "seed": "Agriculture / Agritech",
    "seeds": "Agriculture / Agritech",
    "crop": "Agriculture / Agritech",
    "irrigation": "Agriculture / Agritech",

    # Metals / Steel / Cement / Building Materials
    "tata steel": "Steel / Metals",
    "jsw steel": "Steel / Metals",
    "sail": "Steel / Metals",
    "jindal steel": "Steel / Metals",
    "hindalco": "Metals",
    "vedanta": "Metals",
    "steel": "Steel / Metals",
    "metal": "Metals",
    "metals": "Metals",
    "aluminium": "Metals",
    "copper": "Metals",
    "cement": "Cement / Building Materials",
    "ultratech": "Cement / Building Materials",
    "ambuja": "Cement / Building Materials",
    "acc cement": "Cement / Building Materials",
    "building material": "Cement / Building Materials",
    "construction material": "Cement / Building Materials",

    # Oil & Gas / Energy
    "iocl": "Oil & Gas",
    "indian oil": "Oil & Gas",
    "ongc": "Oil & Gas",
    "bpcl": "Oil & Gas",
    "hpcl": "Oil & Gas",
    "shell": "Oil & Gas",
    "castrol": "Oil & Gas",
    "oil & gas": "Oil & Gas",
    "oil and gas": "Oil & Gas",
    "refinery": "Oil & Gas",
    "lubricant": "Oil & Gas",
    "petroleum": "Oil & Gas",
    "energy": "Energy / Infrastructure",
    "power": "Energy / Infrastructure",

    # Logistics / Supply Chain / Warehousing
    "logistics": "Logistics",
    "supply chain": "Logistics",
    "warehouse": "Logistics",
    "warehousing": "Logistics",
    "distribution": "Logistics",
    "last mile": "Logistics",
    "transport": "Logistics",
    "dispatch": "Logistics",
    "inventory": "Logistics",

    # Construction / Infrastructure / Industrial
    "l&t": "Construction / Infrastructure",
    "larsen and toubro": "Construction / Infrastructure",
    "adani": "Energy / Infrastructure",
    "construction": "Construction / Infrastructure",
    "infrastructure": "Construction / Infrastructure",
    "project site": "Construction / Infrastructure",
    "epc": "Construction / Infrastructure",
    "contracting": "Construction / Infrastructure",

    # Generic manufacturing
    "manufacturing": "Manufacturing",
    "manufacturer": "Manufacturing",
    "production": "Manufacturing",
    "factory": "Manufacturing",
    "plant": "Manufacturing",
}


def _normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("&", " and ")
    value = value.replace("/", " ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def get_candidate_industry(resume_text: str, filename: str = "") -> str:
    """
    Returns a clean industry label for Indian non-IT hiring.
    Used as a deterministic fallback when AI scoring does not provide
    a useful industry label.
    """
    text = _normalize_text(f"{resume_text or ''} {filename or ''}")
    if not text:
        return "Others / Not Detected"

    for keyword, industry in INDIA_INDUSTRY_MAP.items():
        kw = _normalize_text(keyword)
        if kw and kw in text:
            return industry

    if any(word in text for word in [
        "factory", "plant", "unit", "production", "manufacturer", "manufacturing"
    ]):
        return "Manufacturing"

    return "Others / Not Detected"

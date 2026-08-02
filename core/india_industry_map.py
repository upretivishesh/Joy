# core/india_industry_map.py

import re
from collections import defaultdict


INDUSTRY_PATTERNS = {
    "Automotive": [
        "tata motors", "mahindra", "maruti", "hero motocorp", "hero", "tvs",
        "bajaj auto", "ashok leyland", "eicher", "bosch", "motherson",
        "automotive", "automobile", "auto component", "autocomponent",
        "vehicle", "oem", "2 wheeler", "4 wheeler", "commercial vehicle",
        "passenger vehicle", "tractor"
    ],

    "FMCG": [
        "hul", "hindustan unilever", "itc", "dabur", "nestle", "britannia",
        "marico", "gcpl", "godrej consumer", "emami", "reckitt", "pepsico",
        "cocacola", "coca cola", "fmcg", "consumer goods",
        "fast moving consumer goods", "foods", "food products", "beverages",
        "personal care", "home care", "oral care", "packaged foods"
    ],

    "Retail": [
        "reliance retail", "dmart", "avenue supermarts", "zepto", "blinkit",
        "bigbasket", "flipkart", "amazon", "nykaa", "myntra", "retail",
        "modern trade", "general trade", "ecommerce", "e commerce",
        "omnichannel", "store operations", "merchandising", "d2c",
        "direct to consumer", "dtc"
    ],

    "Pharmaceuticals": [
        "sun pharma", "cipla", "dr reddy", "dr. reddy", "lupin", "torrent pharma",
        "zydus", "alkem", "mankind", "glenmark", "ipca", "pharma",
        "pharmaceutical", "pharmaceuticals", "formulation", "formulations",
        "api", "bulk drug", "tablet", "capsule", "injectable", "healthcare",
        "life sciences"
    ],

    "Agrochemicals": [
        "upl", "coromandel", "pi industries", "sumitomo chemical", "syngenta",
        "bayer crop science", "rallis", "dhanuka", "insecticides india",
        "best agrolife", "agrochemical", "agro chemical", "agrochemicals",
        "crop protection", "pesticide", "pesticides", "herbicide", "herbicides",
        "fungicide", "fungicides", "insecticide", "insecticides",
        "fertilizer", "fertilizers", "fertiliser", "fertilisers",
        "plant nutrition", "crop care"
    ],

    "Agriculture / Agritech": [
        "agri", "agriculture", "agricultural", "agritech", "farm input",
        "farm inputs", "seed", "seeds", "crop", "crops", "irrigation",
        "soil health", "farmer", "farming", "horticulture", "nursery"
    ],

    "Chemicals": [
        "pidilite", "basf", "deepak nitrite", "aarti industries", "navin fluorine",
        "tatva chintan", "speciality chemical", "speciality chemicals",
        "specialty chemical", "specialty chemicals", "chemical", "chemicals",
        "industrial chemical", "solvent", "solvents", "resin", "resins",
        "petrochemical", "petrochemicals", "adhesive", "adhesives"
    ],

    "Paints / Chemicals": [
        "asian paints", "berger paints", "kansai nerolac", "akzonobel",
        "paint", "paints", "coating", "coatings", "decorative paint",
        "industrial paint"
    ],

    "Steel / Metals": [
        "tata steel", "jsw steel", "sail", "jindal steel", "steel",
        "rolled steel", "flat steel", "long steel", "metal", "metals",
        "foundry", "forging", "forgings"
    ],

    "Metals": [
        "hindalco", "vedanta", "nalco", "aluminium", "aluminum", "copper",
        "zinc", "smelter", "extrusion"
    ],

    "Cement / Building Materials": [
        "ultratech", "ambuja", "acc cement", "shree cement", "dalmia cement",
        "jk cement", "cement", "ready mix concrete", "rmc", "building material",
        "building materials", "construction material", "construction materials",
        "tiles", "plywood", "sanitaryware", "pipes"
    ],

    "Oil & Gas": [
        "iocl", "indian oil", "ongc", "bpcl", "hpcl", "shell", "castrol",
        "oil and gas", "oil gas", "oil", "gas", "refinery", "refineries",
        "lubricant", "lubricants", "petroleum", "downstream", "upstream"
    ],

    "Energy / Infrastructure": [
        "adani", "ntpc", "power grid", "tata power", "renewable",
        "renewables", "solar", "wind energy", "energy", "power",
        "transmission", "distribution utility", "infra", "infrastructure"
    ],

    "Construction / Infrastructure": [
        "l&t", "larsen and toubro", "construction", "epc", "project site",
        "contracting", "real estate", "civil", "structural", "site execution",
        "site engineer", "infrastructure project"
    ],

    "Logistics": [
        "logistics", "supply chain", "warehouse", "warehousing", "distribution",
        "transport", "transportation", "freight", "dispatch", "inventory",
        "last mile", "cold chain", "3pl", "shipment"
    ],

    "Manufacturing": [
        "manufacturing", "manufacturer", "production", "factory", "plant",
        "assembly line", "process plant", "unit"
    ],

    "Electrical / Electronics": [
        "electrical", "electronics", "consumer electronics", "pcb", "semiconductor",
        "transformer", "switchgear", "wiring", "cable", "appliance"
    ],

    "Telecom": [
        "telecom", "telecommunications", "airtel", "jio", "vodafone idea",
        "vi", "tower", "fiber", "broadband", "network rollout"
    ],

    "Banking / Financial Services": [
        "bank", "banking", "nbfc", "insurance", "loan", "lending", "mortgage",
        "wealth", "asset management", "financial services", "finserv"
    ],

    "Textiles / Apparel": [
        "textile", "textiles", "garment", "garments", "apparel", "fashion retail",
        "fabric", "spinning", "weaving", "knitting", "dyeing"
    ],

    "Packaging": [
        "packaging", "flexible packaging", "rigid packaging", "label", "labels",
        "carton", "corrugated", "blow molding", "injection molding"
    ],

    "Paper / Packaging": [
        "paper", "pulp", "kraft", "corrugation", "corrugated box"
    ],

    "Mining / Minerals": [
        "mining", "minerals", "quarry", "ore", "coal", "limestone", "bauxite"
    ],

    "Consumer Durables": [
        "consumer durable", "consumer durables", "white goods", "refrigerator",
        "washing machine", "air conditioner", "ac sales", "home appliance",
        "durable sales"
    ],
}


INDUSTRY_PRIORITY = {
    "Agrochemicals": 120,
    "Pharmaceuticals": 120,
    "Paints / Chemicals": 115,
    "Cement / Building Materials": 115,
    "Chemicals": 110,
    "FMCG": 110,
    "Retail": 110,
    "Automotive": 110,
    "Oil & Gas": 110,
    "Energy / Infrastructure": 105,
    "Construction / Infrastructure": 105,
    "Steel / Metals": 105,
    "Metals": 100,
    "Agriculture / Agritech": 100,
    "Electrical / Electronics": 100,
    "Telecom": 100,
    "Banking / Financial Services": 100,
    "Textiles / Apparel": 100,
    "Packaging": 98,
    "Paper / Packaging": 96,
    "Mining / Minerals": 96,
    "Consumer Durables": 96,
    "Logistics": 90,
    "Manufacturing": 70,
}


GENERIC_PENALTY_TERMS = {
    "plant", "production", "factory", "unit", "manufacturing", "manufacturer",
    "logistics", "distribution", "inventory", "dispatch", "warehouse"
}


def _normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("&", " and ")
    value = value.replace("/", " ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\bdr\.\b", "dr", value)
    value = re.sub(r"\be[-\s]?commerce\b", "ecommerce", value)
    value = re.sub(r"\bd2c\b", "direct to consumer", value)
    value = re.sub(r"\bdtc\b", "direct to consumer", value)
    value = re.sub(r"\bfmcg\b", "fast moving consumer goods", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _keyword_weight(keyword: str) -> int:
    words = keyword.split()
    if len(words) >= 3:
        return 18
    if len(words) == 2:
        return 10
    if keyword in GENERIC_PENALTY_TERMS:
        return 4
    return 6


def get_candidate_industry(resume_text: str, filename: str = "") -> str:
    """
    Returns the best-fit industry label for Indian non-IT hiring.
    Uses weighted multi-match scoring so specific industries beat generic ones.
    """
    text = _normalize_text(f"{resume_text or ''} {filename or ''}")
    if not text:
        return "Others / Not Detected"

    scores = defaultdict(int)

    for industry, keywords in INDUSTRY_PATTERNS.items():
        for raw_kw in keywords:
            kw = _normalize_text(raw_kw)
            if not kw:
                continue
            if kw in text:
                scores[industry] += _keyword_weight(kw)

        if scores[industry]:
            scores[industry] += INDUSTRY_PRIORITY.get(industry, 0)

    if not scores:
        if any(word in text for word in ["factory", "plant", "unit", "production", "manufacturer", "manufacturing"]):
            return "Manufacturing"
        return "Others / Not Detected"

    best_industry = max(scores.items(), key=lambda item: item[1])[0]
    return best_industry

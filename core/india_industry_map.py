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

    # API / process chemistry signals (pharma OR agro route scouting, scale-up,
    # PR&D) — must come BEFORE the generic "chemical" catch-all below, and
    # BEFORE plain "pharma", so a resume doesn't get silently bucketed into
    # generic "Chemicals" just because it never says the word "agrochemical"
    # or "pharmaceutical" outright. This is the process-chemistry skillset
    # Atomgrid actually needs regardless of which end molecule it was applied to.
    ("route scouting", "API / Process Chemistry (Pharma or Agro)"),
    ("route scoutting", "API / Process Chemistry (Pharma or Agro)"),
    ("process r&d", "API / Process Chemistry (Pharma or Agro)"),
    ("process rd", "API / Process Chemistry (Pharma or Agro)"),
    ("pr&d", "API / Process Chemistry (Pharma or Agro)"),
    ("process research", "API / Process Chemistry (Pharma or Agro)"),
    ("process development", "API / Process Chemistry (Pharma or Agro)"),
    ("scale up", "API / Process Chemistry (Pharma or Agro)"),
    ("scale-up", "API / Process Chemistry (Pharma or Agro)"),
    ("pilot plant", "API / Process Chemistry (Pharma or Agro)"),
    ("active pharmaceutical ingredient", "API / Process Chemistry (Pharma or Agro)"),
    ("active pharmaceutical ingredients", "API / Process Chemistry (Pharma or Agro)"),
    ("api synthesis", "API / Process Chemistry (Pharma or Agro)"),
    ("api intermediate", "API / Process Chemistry (Pharma or Agro)"),
    ("api intermediates", "API / Process Chemistry (Pharma or Agro)"),
    ("drug intermediate", "API / Process Chemistry (Pharma or Agro)"),
    ("drug intermediates", "API / Process Chemistry (Pharma or Agro)"),
    ("technology transfer", "API / Process Chemistry (Pharma or Agro)"),
    ("tech transfer", "API / Process Chemistry (Pharma or Agro)"),
    ("impurity profiling", "API / Process Chemistry (Pharma or Agro)"),
    ("multi step synthesis", "API / Process Chemistry (Pharma or Agro)"),
    ("multistep synthesis", "API / Process Chemistry (Pharma or Agro)"),
    ("new chemical entity", "API / Process Chemistry (Pharma or Agro)"),
    ("new chemical entities", "API / Process Chemistry (Pharma or Agro)"),

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

        # Fashion / apparel / textiles
    ("fashion", "Fashion & Apparel"),
    ("apparel", "Fashion & Apparel"),
    ("garment", "Fashion & Apparel"),
    ("garments", "Fashion & Apparel"),
    ("textile", "Fashion & Apparel"),
    ("textiles", "Fashion & Apparel"),
    ("retail fashion", "Fashion & Apparel"),

    # Interior design / interiors / architecture
    ("interior design", "Interior Design"),
    ("interiors", "Interior Design"),
    ("interior decorator", "Interior Design"),
    ("interior decorating", "Interior Design"),
    ("space planning", "Interior Design"),
    ("architecture interior", "Interior Design"),
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

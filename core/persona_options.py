"""
Curated option lists for the Client Persona panel.

Kept as plain lists (not enums) so `list_to_use = INDUSTRY_OPTIONS + [custom]`
style merging in app.py stays trivial. Order is deliberate: Seven Hiring's
actual niches first (Atomgrid-style D2C/agro/organic clients are the daily
bread and butter), then a broad sweep of everything else a non-IT recruiter
in India will realistically type into this field.

If a client's true industry isn't here, the persona UI lets Vishesh type it
in directly (via accept_new_options=True on the multiselect) — this list is
a head start, not a cage.
"""

INDUSTRY_OPTIONS: list[str] = [
    # Seven Hiring's core niches — always visible at the top
    "D2C / Direct-to-Consumer",
    "Agrochemicals & Crop Protection",
    "Organic & Regenerative Farming",
    "Interior Design & Architecture",
    "Diamond & Jewellery",
    "Hospitality & Hotels",

    # Adjacent consumer / lifestyle
    "FMCG",
    "Food & Beverage",
    "Food Processing & Packaging",
    "Furniture & Home Decor",
    "Luxury Goods & Lifestyle",
    "Fashion & Apparel",
    "Beauty & Personal Care",
    "E-commerce & Marketplaces",
    "Retail",
    "Sports, Fitness & Wellness",
    "Travel & Tourism",

    # Industrial / manufacturing
    "Chemicals & Specialty Chemicals",
    "Manufacturing (General)",
    "Automotive & EV",
    "Industrial Equipment & Capital Goods",
    "Textiles & Yarn",
    "Plastics & Polymers",
    "Electronics & Semiconductors",
    "Metals, Mining & Steel",
    "Cement & Building Materials",
    "Oil, Gas & Energy",
    "Renewable Energy",
    "Agriculture (Conventional)",
    "Dairy & Animal Husbandry",
    "Honey & Apiculture",

    # Real estate / infra
    "Real Estate & Construction",
    "Engineering, Procurement & Construction (EPC)",

    # Healthcare / science
    "Pharmaceuticals",
    "Biotechnology",
    "Healthcare & Hospitals",

    # Services / white collar
    "IT / Software / SaaS",
    "IT Services & Consulting",
    "Banking & Financial Services",
    "NBFC & Lending",
    "Insurance",
    "Fintech",
    "Management & Strategy Consulting",
    "Legal Services",
    "Human Resources & Staffing",
    "Media, Advertising & Entertainment",
    "EdTech & Education",
    "Telecom",
    "Aviation & Aerospace",
    "Logistics & Supply Chain",
    "Warehousing & Distribution",

    # Catch-alls
    "Public Sector / Government",
    "NGO / Social Sector",
    "Other",
]

LANGUAGE_OPTIONS: list[str] = [
    "English",
    "Hindi",
    "Punjabi",
    "Gujarati",
    "Marathi",
    "Bengali",
    "Tamil",
    "Telugu",
    "Kannada",
    "Malayalam",
    "Odia",
    "Assamese",
    "Urdu",
    "Rajasthani / Marwari",
    "Bhojpuri",
    "Konkani",
    "Sindhi",
    "Kashmiri",
    "Nepali",
    "Mandarin (Chinese)",
    "Any regional language",
    "No language requirement",
]


def merge_with_custom(base_options: list[str], saved_values: list[str] | None) -> list[str]:
    """
    Make sure anything already saved on a persona (including old custom
    entries typed in before this list existed, or values added later via
    accept_new_options) still shows up as a selectable/selected option even
    if it isn't in the curated base list. Prevents the classic Streamlit
    'default value not in options -> silently dropped' bug.
    """
    merged = list(base_options)
    for value in saved_values or []:
        if value and value not in merged:
            merged.append(value)
    return merged

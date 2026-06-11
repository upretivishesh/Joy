import re
from pathlib import Path

APP_NAME = "Joy"
DEFAULT_COMPANY = "Seven Hiring"
DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"

DATE_RANGE_REGEX = re.compile(
    r"""
    (?:
        (jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|
         january|february|march|april|june|july|august|september|
         october|november|december)?
        [\s'.,/-]*
    )
    ((?:19|20)\d{2})
    \s*(?:-|to|till|until|through|--|->|presently|currently|\u2013|\u2014)\s*
    (?:
        (present|current|currently|till\s+date|till\s+now|ongoing)|
        (?:
            (jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|
             january|february|march|april|june|july|august|september|
             october|november|december)?
            [\s'.,/-]*
        )
        ((?:19|20)\d{2})
    )
    """,
    re.I | re.X,
)

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

SKILL_ALIASES = {
    "photoshop": ["photoshop", "adobe photoshop", "ps"],
    "illustrator": ["illustrator", "adobe illustrator"],
    "indesign": ["indesign", "adobe indesign"],
    "figma": ["figma"],
    "canva": ["canva"],
    "coreldraw": ["coreldraw", "corel draw"],
    "after effects": ["after effects", "aftereffects"],
    "premiere pro": ["premiere pro", "premiere"],
    "branding": ["branding", "brand identity"],
    "social media design": ["social media design", "instagram creatives"],
    "visual merchandising": ["visual merchandising"],
    "autocad": ["autocad", "auto cad"],
    "sketchup": ["sketchup", "sketch up"],
    "3ds max": ["3ds max", "3d max"],
    "vray": ["vray", "v-ray"],
    "revit": ["revit"],
    "lumion": ["lumion"],
    "space planning": ["space planning"],
    "site supervision": ["site supervision", "site execution"],
    "interior design": ["interior design", "interior designing"],
    "modular furniture": ["modular furniture"],
    "residential projects": ["residential projects"],
    "commercial projects": ["commercial projects"],
    "tally": ["tally", "tally erp"],
    "gst": ["gst"],
    "tds": ["tds"],
    "accounting": ["accounting", "bookkeeping"],
    "financial analysis": ["financial analysis"],
    "budgeting": ["budgeting", "budget planning"],
    "bank reconciliation": ["bank reconciliation"],
    "accounts payable": ["accounts payable", "ap"],
    "accounts receivable": ["accounts receivable", "ar"],
    "invoice processing": ["invoice processing"],
    "taxation": ["taxation"],
    "mis reporting": ["mis reporting", "mis"],
    "quickbooks": ["quickbooks"],
    "production planning": ["production planning"],
    "inventory management": ["inventory management"],
    "quality control": ["quality control", "qc"],
    "quality assurance": ["quality assurance", "qa"],
    "lean manufacturing": ["lean manufacturing"],
    "six sigma": ["six sigma"],
    "supply chain": ["supply chain"],
    "procurement": ["procurement", "purchasing"],
    "vendor management": ["vendor management"],
    "warehouse operations": ["warehouse operations"],
    "dispatch": ["dispatch"],
    "logistics": ["logistics"],
    "bom": ["bom", "bill of materials"],
    "production scheduling": ["production scheduling"],
    "channel sales": ["channel sales"],
    "territory sales": ["territory sales"],
    "b2b sales": ["b2b sales"],
    "b2c sales": ["b2c sales"],
    "dealer management": ["dealer management"],
    "distribution": ["distribution"],
    "key account management": ["key account management", "kam"],
    "business development": ["business development", "bd"],
    "lead generation": ["lead generation"],
    "inside sales": ["inside sales"],
    "field sales": ["field sales"],
    "retail sales": ["retail sales"],
    "sales target": ["sales target", "target achievement"],
    "client relationship": ["client relationship", "client handling"],
    "recruitment": ["recruitment", "talent acquisition"],
    "screening": ["screening", "resume screening"],
    "sourcing": ["sourcing", "candidate sourcing"],
    "bulk hiring": ["bulk hiring"],
    "payroll": ["payroll"],
    "employee engagement": ["employee engagement"],
    "hr operations": ["hr operations"],
    "onboarding": ["onboarding"],
    "attendance management": ["attendance management"],
    "operations management": ["operations management"],
    "team handling": ["team handling", "team management"],
    "process improvement": ["process improvement"],
    "coordination": ["coordination"],
    "client servicing": ["client servicing"],
    "documentation": ["documentation"],
    "reporting": ["reporting"],
    "excel": ["excel", "ms excel", "microsoft excel"],
    "communication": ["communication"],
    "leadership": ["leadership"],
    "kitchen operations": ["kitchen operations"],
    "food preparation": ["food preparation"],
    "food safety": ["food safety"],
    "hotel management": ["hotel management"],
    "housekeeping": ["housekeeping"],
    "restaurant operations": ["restaurant operations"],
    "inventory control": ["inventory control"],
    "hardware networking": ["hardware networking"],
    "it support": ["it support"],
    "system administration": ["system administration"],
    "cctv": ["cctv"],
}

STOP_WORDS = {
    "about", "above", "after", "again", "against", "also", "among", "and",
    "any", "are", "based", "been", "being", "best", "between", "both",
    "business", "candidate", "candidates", "client", "company", "description",
    "detail", "details", "development", "each", "etc", "experience",
    "experienced", "for", "from", "good", "have", "hiring", "including",
    "india", "into", "job", "knowledge", "like", "looking", "management",
    "manager", "must", "need", "needs", "our", "over", "preferred", "profile",
    "required", "requirements", "responsibilities", "role", "should", "skill",
    "skills", "strong", "team", "that", "the", "their", "this", "through",
    "with", "work", "working", "years", "you", "your",
}

DEFAULT_QUESTIONS = [
    "Current CTC",
    "Expected CTC",
    "Notice period",
    "Current location",
    "Preferred work location",
    "Total experience",
    "Reason for job change",
    "Current company and designation",
    "Any offer in hand",
    "Suitable slot for a 5-minute discussion",
]

GENERIC_EMAIL_PREFIXES = {
    "admin", "career", "careers", "contact", "cv", "hello", "hr", "info",
    "jobs", "mail", "me", "naukri", "recruitment", "resume", "support",
    "talent", "team", "test",
}

NAME_STOPWORDS = {
    "resume", "curriculum", "vitae", "profile", "email", "phone", "mobile",
    "linkedin", "github", "portfolio", "address", "summary", "objective",
    "education", "experience", "employment", "project", "projects", "skills",
    "certification", "certifications", "developer", "engineer", "manager",
    "analyst", "consultant", "specialist", "executive", "assistant", "designer",
    "architect", "lead", "intern", "recruiter", "marketer", "accountant",
    "professional", "work", "career", "personal", "details", "declaration",
}

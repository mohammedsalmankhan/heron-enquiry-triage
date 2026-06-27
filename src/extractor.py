"""
extractor.py
Rule-based information extraction for joinery customer enquiries.

Design note: this uses regex + keyword matching rather than calling an LLM API,
so it runs fully offline with no API key and no per-request cost. This is the
right tradeoff for a fixed, well-defined extraction task with a small product
vocabulary (windows/doors), where the failure modes of a rule-based system are
easier to predict, test, and explain to a non-technical estimator than a
black-box model. An LLM-based version is a natural next step once real Heron
enquiry data is available to validate prompts against (see README, "Path to
Production").
"""

import re
import json
from dataclasses import dataclass, asdict, field


PRODUCT_KEYWORDS = {
    "sash window": "Sash Window",
    "casement window": "Casement Window",
    "tilt and turn": "Tilt and Turn Window",
    "reversible window": "Reversible Window",
    "sliding window": "Sliding Window",
    "french door": "French Door",
    "fire door": "Fire Door",
    "front door": "Front Door",
    "side panel": "Side Panel (Glazed)",
    "window": "Window (type unspecified)",
    "door": "Door (type unspecified)",
}

MATERIAL_KEYWORDS = {
    "oak": "Oak",
    "softwood": "Softwood",
    "hardwood": "Hardwood",
    "aluminium-clad": "Aluminium-clad Timber",
    "aluminium": "Aluminium-clad Timber",
    "timber": "Timber (unspecified species)",
}

URGENCY_RULES = [
    (r"\b(urgent|asap|as soon as possible|today|this week|time critical)\b", "Urgent"),
    (r"\b(no rush|no firm dates|flexible|early planning|gathering quotes)\b", "Low / Exploratory"),
]

# Crude lead-time extraction: looks for "X weeks", "by <month>", "within X weeks/days"
TIMEFRAME_PATTERNS = [
    r"within (the next )?\d+\s*(day|days|week|weeks)",
    r"\d+\s*(day|days|week|weeks)\s*(from order|lead time)?",
    r"by (the end of )?(january|february|march|april|may|june|july|august|september|october|november|december)",
    r"before (christmas|spring|the end of \w+)",
]

DIMENSION_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|m)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(mm|m)", re.IGNORECASE
)

QUANTITY_PATTERN = re.compile(
    r"\b(\d+)\s*(sash windows?|casement windows?|tilt and turn|reversible windows?|"
    r"sliding windows?|french doors?|fire doors?|front doors?|windows?|doors?|units?)\b",
    re.IGNORECASE,
)


@dataclass
class ExtractedEnquiry:
    enquiry_id: str
    product_types: list = field(default_factory=list)
    quantity: int | None = None
    dimensions_mm: list = field(default_factory=list)
    material: str | None = None
    urgency: str = "Standard / Unclassified"
    timeframe_mentions: list = field(default_factory=list)
    is_commercial: bool = False
    raw_excerpt: str = ""
    extraction_confidence: str = "Medium"  # Low / Medium / High, see notes
    notes: list = field(default_factory=list)


def normalize_dimension(value: str, unit: str) -> float:
    """Convert to millimetres for consistent storage."""
    value = float(value)
    return value * 1000 if unit.lower() == "m" else value


def extract_dimensions(text: str) -> list[dict]:
    results = []
    for match in DIMENSION_PATTERN.finditer(text):
        w_val, w_unit, h_val, h_unit = match.groups()
        results.append({
            "width_mm": round(normalize_dimension(w_val, w_unit), 1),
            "height_mm": round(normalize_dimension(h_val, h_unit), 1),
            "source_text": match.group(0),
        })
    return results


def extract_products(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for keyword, label in PRODUCT_KEYWORDS.items():
        if keyword in text_lower and label not in found:
            # Skip the generic "window"/"door" fallback if a specific type was already found
            found.append(label)
    # De-duplicate generic fallback if a specific type exists
    specific = [f for f in found if "unspecified" not in f]
    if specific:
        found = specific
    return found


def extract_material(text: str) -> str | None:
    text_lower = text.lower()
    for keyword, label in MATERIAL_KEYWORDS.items():
        if keyword in text_lower:
            return label
    return None


def extract_quantity(text: str) -> int | None:
    match = QUANTITY_PATTERN.search(text)
    if match:
        return int(match.group(1))
    return None


def extract_urgency(text: str) -> str:
    text_lower = text.lower()
    for pattern, label in URGENCY_RULES:
        if re.search(pattern, text_lower):
            return label
    return "Standard / Unclassified"


def extract_timeframes(text: str) -> list[str]:
    text_lower = text.lower()
    matches = []
    for pattern in TIMEFRAME_PATTERNS:
        for m in re.finditer(pattern, text_lower):
            matches.append(m.group(0))
    return matches


def detect_commercial(text: str) -> bool:
    commercial_signals = [
        "contractor", "trade quote", "development", "office fit-out", "lease",
        "school", "procurement", "care home", "shopfront", "business licence",
        "ltd", "construction", "property group",
    ]
    text_lower = text.lower()
    return any(signal in text_lower for signal in commercial_signals)


def assess_confidence(extracted: ExtractedEnquiry) -> str:
    """
    Simple, explainable confidence heuristic: an estimator should be able to
    see WHY the system is unsure, not just a number. This is far more useful
    in a small business handoff than a black-box probability score.
    """
    missing = []
    if not extracted.product_types:
        missing.append("product type")
    if not extracted.dimensions_mm:
        missing.append("dimensions")
    if not extracted.material:
        missing.append("material")

    if len(missing) == 0:
        return "High"
    elif len(missing) <= 1:
        extracted.notes.append(f"Missing: {', '.join(missing)} — recommend manual follow-up.")
        return "Medium"
    else:
        extracted.notes.append(f"Missing: {', '.join(missing)} — high manual review priority.")
        return "Low"


def extract_enquiry(enquiry_id: str, text: str) -> ExtractedEnquiry:
    dims = extract_dimensions(text)
    result = ExtractedEnquiry(
        enquiry_id=enquiry_id,
        product_types=extract_products(text),
        quantity=extract_quantity(text),
        dimensions_mm=dims,
        material=extract_material(text),
        urgency=extract_urgency(text),
        timeframe_mentions=extract_timeframes(text),
        is_commercial=detect_commercial(text),
        raw_excerpt=text[:160] + ("..." if len(text) > 160 else ""),
    )
    result.extraction_confidence = assess_confidence(result)
    return result


def load_enquiries(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_batch(input_path: str) -> list[dict]:
    enquiries = load_enquiries(input_path)
    results = []
    for enquiry in enquiries:
        extracted = extract_enquiry(enquiry["id"], enquiry["raw_text"])
        results.append(asdict(extracted))
    return results


if __name__ == "__main__":
    import sys
    input_file = sys.argv[1] if len(sys.argv) > 1 else "data/sample_enquiries.json"
    output = run_batch(input_file)
    print(json.dumps(output, indent=2))

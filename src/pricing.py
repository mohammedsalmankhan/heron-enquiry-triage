"""
pricing.py
Rough cost-estimation engine from extracted enquiry fields.

These base rates are illustrative placeholders, not real Heron pricing —
deliberately, since I have no access to their actual cost data. The point
of this module is to demonstrate the LOGIC of going from structured fields
to a defensible estimate range, in a way that is trivially easy to swap
real rates into. See README for what would be needed to make this production
accurate.
"""

from dataclasses import dataclass

# Illustrative base rate per square metre (GBP), by product type and material.
# Placeholder figures only — see module docstring.
BASE_RATES_PER_SQM = {
    ("Sash Window", "Oak"): 620,
    ("Sash Window", "Timber (unspecified species)"): 540,
    ("Casement Window", "Softwood"): 310,
    ("Casement Window", "Hardwood"): 480,
    ("Tilt and Turn Window", "Aluminium-clad Timber"): 580,
    ("Reversible Window", "Timber (unspecified species)"): 350,
    ("French Door", "Oak"): 690,
    ("Fire Door", "Timber (unspecified species)"): 450,
    ("Front Door", "Oak"): 750,
}

DEFAULT_RATE_PER_SQM = 400  # fallback when product/material combo not in table
URGENCY_SURCHARGE = {
    "Urgent": 0.20,        # rush jobs cost more to schedule in
    "Low / Exploratory": 0.0,
    "Standard / Unclassified": 0.0,
}
COMMERCIAL_DISCOUNT = 0.08  # illustrative trade/volume discount
QUANTITY_DISCOUNT_THRESHOLD = 5
QUANTITY_DISCOUNT_RATE = 0.05


@dataclass
class PriceEstimate:
    enquiry_id: str
    estimate_low_gbp: float | None
    estimate_high_gbp: float | None
    basis: str
    confidence: str
    flags: list


def estimate_price(extracted: dict) -> PriceEstimate:
    enquiry_id = extracted["enquiry_id"]
    flags = []

    if not extracted["dimensions_mm"] or not extracted["product_types"]:
        return PriceEstimate(
            enquiry_id=enquiry_id,
            estimate_low_gbp=None,
            estimate_high_gbp=None,
            basis="Insufficient data for estimate",
            confidence="None",
            flags=["Missing dimensions or product type — manual quote required"],
        )

    product = extracted["product_types"][0]
    material = extracted["material"] or "Timber (unspecified species)"
    quantity = extracted["quantity"] or 1

    rate = BASE_RATES_PER_SQM.get((product, material))
    if rate is None:
        rate = DEFAULT_RATE_PER_SQM
        flags.append(f"No specific rate for {product} / {material} — used default rate, verify manually")

    total_area_sqm = 0.0
    for dim in extracted["dimensions_mm"]:
        area = (dim["width_mm"] / 1000) * (dim["height_mm"] / 1000)
        total_area_sqm += area

    if total_area_sqm == 0:
        total_area_sqm = 1.0  # safety fallback, shouldn't trigger given the guard above

    base_cost = rate * total_area_sqm * quantity

    surcharge = URGENCY_SURCHARGE.get(extracted["urgency"], 0.0)
    if surcharge:
        flags.append(f"Urgency surcharge applied (+{int(surcharge*100)}%) — confirm before quoting")

    discount = 0.0
    if extracted["is_commercial"]:
        discount += COMMERCIAL_DISCOUNT
        flags.append("Commercial/trade discount applied — confirm account status")
    if quantity >= QUANTITY_DISCOUNT_THRESHOLD:
        discount += QUANTITY_DISCOUNT_RATE
        flags.append("Volume discount applied for quantity >= 5")

    adjusted_cost = base_cost * (1 + surcharge) * (1 - discount)

    # Present as a range rather than a false-precision single number
    low = round(adjusted_cost * 0.9, -1)
    high = round(adjusted_cost * 1.15, -1)

    basis = (
        f"{quantity} x {product} ({material}), {total_area_sqm:.2f} sqm total, "
        f"base rate £{rate}/sqm"
    )

    return PriceEstimate(
        enquiry_id=enquiry_id,
        estimate_low_gbp=low,
        estimate_high_gbp=high,
        basis=basis,
        confidence=extracted["extraction_confidence"],
        flags=flags,
    )

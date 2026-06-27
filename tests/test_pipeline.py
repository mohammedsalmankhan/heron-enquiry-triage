"""
test_pipeline.py
Unit tests for the enquiry triage extraction and pricing logic.

Run with: pytest tests/ -v   (from project root)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from extractor import (
    extract_dimensions, extract_products, extract_material,
    extract_quantity, extract_urgency, detect_commercial, extract_enquiry,
)
from pricing import estimate_price


# --- Dimension extraction ---

def test_dimension_extraction_mm():
    dims = extract_dimensions("size (900mm x 1200mm)")
    assert len(dims) == 1
    assert dims[0]["width_mm"] == 900
    assert dims[0]["height_mm"] == 1200


def test_dimension_extraction_metres_converted_to_mm():
    dims = extract_dimensions("1.4m x 1.8m each")
    assert len(dims) == 1
    assert dims[0]["width_mm"] == 1400
    assert dims[0]["height_mm"] == 1800


def test_dimension_extraction_known_limitation_omitted_unit():
    """
    Documents a second known limitation: when only the second number has a
    unit (e.g. '1.4 x 1.8m'), the regex requires units on both numbers and
    will not match. In the real ENQ-004 sample this enquiry correctly falls
    back to 'manual quote required' rather than guessing the unit.
    """
    dims = extract_dimensions("1.4 x 1.8m each")
    assert dims == []  # confirms current (limited) behaviour


def test_dimension_extraction_known_limitation_natural_phrasing():
    """
    Documents a known limitation: 'wide by ... tall' phrasing is not
    currently matched. This test exists so the limitation is visible
    and intentional, not a silent gap.
    """
    dims = extract_dimensions("roughly 1.2m wide by 1.5m tall")
    assert dims == []  # confirms current (limited) behaviour


def test_mm_not_misread_as_metres():
    """
    Regression test for a real bug found during development: the original
    regex alternation (m|mm) greedily matched 'mm' as 'm', causing 1200mm
    to be read as 1200 metres. This caused six-figure price estimates on
    small residential jobs. Fixed by reordering the alternation to (mm|m).
    """
    dims = extract_dimensions("900mm x 1200mm")
    assert dims[0]["width_mm"] == 900
    assert dims[0]["height_mm"] == 1200
    # sanity bound: no residential window should compute as 900 metres
    assert dims[0]["width_mm"] < 5000


# --- Product / material / quantity extraction ---

def test_product_extraction_specific_type():
    products = extract_products("I'm looking for 3 sash windows for my cottage")
    assert products == ["Sash Window"]


def test_product_extraction_prefers_specific_over_generic():
    products = extract_products("looking for a casement window, just one window")
    assert "Casement Window" in products
    assert "Window (type unspecified)" not in products


def test_material_extraction():
    assert extract_material("in oak if possible") == "Oak"
    assert extract_material("softwood, painted white") == "Softwood"
    assert extract_material("no material mentioned here") is None


def test_quantity_extraction():
    assert extract_quantity("3 sash windows for my cottage") == 3
    assert extract_quantity("14 casement windows, all the same size") == 14
    assert extract_quantity("a single oak front door") is None  # known limitation: "a single" not parsed as 1


# --- Urgency and commercial detection ---

def test_urgency_detection_urgent():
    assert extract_urgency("urgent enquiry - need this ASAP") == "Urgent"


def test_urgency_detection_low():
    assert extract_urgency("no rush, just gathering quotes at this stage") == "Low / Exploratory"


def test_urgency_default():
    assert extract_urgency("would like a quote please") == "Standard / Unclassified"


def test_commercial_detection_true():
    assert detect_commercial("we are a building contractor working on a new-build site") is True


def test_commercial_detection_false():
    assert detect_commercial("hi, looking for a quote for my cottage") is False


# --- End-to-end extraction ---

def test_full_extraction_high_confidence_case():
    text = "14 casement windows, all the same size (900mm x 1200mm), softwood, painted white"
    result = extract_enquiry("TEST-001", text)
    assert result.product_types == ["Casement Window"]
    assert result.quantity == 14
    assert result.material == "Softwood"
    assert result.extraction_confidence == "High"


def test_full_extraction_low_confidence_case():
    """Vague enquiry missing product, dimensions, and material should flag as Low confidence."""
    text = "Hi, can you give me a rough idea of cost? No rush."
    result = extract_enquiry("TEST-002", text)
    assert result.extraction_confidence == "Low"
    assert len(result.notes) > 0


# --- Pricing ---

def test_pricing_insufficient_data_returns_none():
    extracted = {
        "enquiry_id": "TEST-003", "product_types": [], "quantity": None,
        "dimensions_mm": [], "material": None, "urgency": "Standard / Unclassified",
        "is_commercial": False, "extraction_confidence": "Low",
    }
    price = estimate_price(extracted)
    assert price.estimate_low_gbp is None
    assert "manual quote required" in price.flags[0].lower()


def test_pricing_sane_range_for_small_residential_job():
    """
    Regression-style sanity check: a single small softwood casement window
    must not price in the hundreds of thousands. This is the exact bug
    class that was caught and fixed in extract_dimensions.
    """
    extracted = {
        "enquiry_id": "TEST-004",
        "product_types": ["Casement Window"],
        "quantity": 1,
        "dimensions_mm": [{"width_mm": 800, "height_mm": 1000, "source_text": "800mm x 1000mm"}],
        "material": "Softwood",
        "urgency": "Standard / Unclassified",
        "is_commercial": False,
        "extraction_confidence": "High",
    }
    price = estimate_price(extracted)
    assert price.estimate_low_gbp is not None
    assert 50 < price.estimate_low_gbp < 2000  # sane bound for one small window
    assert price.estimate_high_gbp > price.estimate_low_gbp


def test_pricing_urgency_surcharge_increases_estimate():
    base = {
        "enquiry_id": "TEST-005", "product_types": ["Fire Door"], "quantity": 1,
        "dimensions_mm": [{"width_mm": 900, "height_mm": 2100, "source_text": ""}],
        "material": None, "is_commercial": False, "extraction_confidence": "Medium",
    }
    standard = estimate_price({**base, "urgency": "Standard / Unclassified"})
    urgent = estimate_price({**base, "urgency": "Urgent"})
    assert urgent.estimate_low_gbp > standard.estimate_low_gbp


def test_pricing_volume_discount_applies_at_threshold():
    extracted = {
        "enquiry_id": "TEST-006", "product_types": ["Casement Window"], "quantity": 6,
        "dimensions_mm": [{"width_mm": 900, "height_mm": 1200, "source_text": ""}],
        "material": "Softwood", "urgency": "Standard / Unclassified",
        "is_commercial": False, "extraction_confidence": "High",
    }
    price = estimate_price(extracted)
    assert any("volume discount" in f.lower() for f in price.flags)

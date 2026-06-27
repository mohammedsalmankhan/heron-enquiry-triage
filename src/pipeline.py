"""
pipeline.py
End-to-end run: load enquiries -> extract structured fields -> estimate price
-> write combined output for the dashboard / review.
"""

import json
from dataclasses import asdict
from extractor import run_batch, load_enquiries, extract_enquiry
from pricing import estimate_price


def run_pipeline(input_path: str, output_path: str) -> list[dict]:
    raw_enquiries = load_enquiries(input_path)
    combined = []

    for enquiry in raw_enquiries:
        extracted = extract_enquiry(enquiry["id"], enquiry["raw_text"])
        extracted_dict = asdict(extracted)
        price = estimate_price(extracted_dict)

        combined.append({
            "enquiry_id": enquiry["id"],
            "raw_text": enquiry["raw_text"],
            "extracted": extracted_dict,
            "price_estimate": asdict(price),
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

    return combined


if __name__ == "__main__":
    results = run_pipeline("data/sample_enquiries.json", "data/pipeline_output.json")
    print(f"Processed {len(results)} enquiries -> data/pipeline_output.json")

    # Quick console summary, useful for a live demo / interview walkthrough
    for r in results:
        ext = r["extracted"]
        price = r["price_estimate"]
        print(f"\n{r['enquiry_id']} | confidence: {ext['extraction_confidence']}")
        print(f"  Product: {ext['product_types']} | Qty: {ext['quantity']} | Material: {ext['material']}")
        print(f"  Urgency: {ext['urgency']} | Commercial: {ext['is_commercial']}")
        if price["estimate_low_gbp"]:
            print(f"  Estimate: £{price['estimate_low_gbp']:.0f} - £{price['estimate_high_gbp']:.0f}")
        else:
            print(f"  Estimate: {price['basis']}")
        if price["flags"]:
            print(f"  Flags: {price['flags']}")

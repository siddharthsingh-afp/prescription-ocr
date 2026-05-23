"""
Prescription OCR using Google Gemini API.
Usage: python gemini_ocr.py <path-to-prescription-image>
"""

import json
import sys
from pathlib import Path

from google import genai
from google.genai import types


EXTRACTION_PROMPT = """You are analyzing a doctor's prescription from India.
A pharmacist will verify your output before any medicine is dispensed.

Extract the following as JSON:
- doctor_name (if visible)
- patient_name (if visible)
- date (if visible)
- diagnosis (if visible)
- medicines: a list, each with these fields:
    - name (as written on prescription, don't substitute brand/generic)
    - strength (e.g., "400 mg", "5%")
    - form (tablet, cream, shampoo, syrup, etc.)
    - dosage (how much per dose)
    - frequency (e.g., "once a week", "twice daily")
    - duration (e.g., "7 days")
    - quantity (total prescribed)
    - confidence ("high", "medium", or "low")
    - notes (only if confidence is medium/low - explain what's unclear)
- warnings: list of strings - anything the pharmacist should watch for
  (illegible doses, Schedule H drugs, similar-sounding medicines, etc.)

Rules:
1. If something is unclear, mark as null and set low confidence. Do NOT guess.
2. Return ONLY valid JSON, no other text, no markdown fences.
"""


def extract_prescription(image_path):
    image_path = Path(image_path)
    if not image_path.exists():
        print(f"Error: File not found: {image_path}")
        sys.exit(1)

    suffix = image_path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }
    if suffix not in mime_types:
        print(f"Error: Unsupported file type {suffix}")
        print("Use .jpg, .jpeg, .png, or .webp")
        sys.exit(1)

    client = genai.Client()

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    print(f"Sending {image_path.name} to Gemini... (this takes 10-30 seconds)")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_types[suffix]),
            EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    raw_text = response.text.strip()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        print("Error: Gemini returned something that isn't valid JSON.")
        print("Raw response:")
        print(raw_text)
        sys.exit(1)

    return data


def print_results(data):
    print("\n" + "=" * 60)
    print("PRESCRIPTION EXTRACTION RESULT (Gemini)")
    print("=" * 60)

    if data.get("doctor_name"):
        print(f"Doctor:    {data['doctor_name']}")
    if data.get("patient_name"):
        print(f"Patient:   {data['patient_name']}")
    if data.get("date"):
        print(f"Date:      {data['date']}")
    if data.get("diagnosis"):
        print(f"Diagnosis: {data['diagnosis']}")

    medicines = data.get("medicines", [])
    print(f"\nMEDICINES FOUND: {len(medicines)}")
    print("-" * 60)
    for i, med in enumerate(medicines, 1):
        conf = (med.get("confidence") or "unknown").upper()
        marker = {"HIGH": "[OK]", "MEDIUM": "[??]", "LOW": "[!!]"}.get(conf, "[?]")
        print(f"\n{i}. {marker} {med.get('name', '???')}", end="")
        if med.get("strength"):
            print(f"  {med['strength']}", end="")
        if med.get("form"):
            print(f"  ({med['form']})", end="")
        print(f"  - confidence: {conf}")
        if med.get("dosage"):
            print(f"   Dosage:    {med['dosage']}")
        if med.get("frequency"):
            print(f"   Frequency: {med['frequency']}")
        if med.get("duration"):
            print(f"   Duration:  {med['duration']}")
        if med.get("quantity"):
            print(f"   Quantity:  {med['quantity']}")
        if med.get("notes"):
            print(f"   Notes:     {med['notes']}")

    warnings = data.get("warnings", [])
    if warnings:
        print("\n" + "-" * 60)
        print("WARNINGS:")
        for w in warnings:
            print(f"  * {w}")

    print("\n" + "=" * 60)
    print("Reminder: pharmacist must verify before dispatch.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python gemini_ocr.py <path-to-prescription-image>")
        sys.exit(1)

    result = extract_prescription(sys.argv[1])
    print_results(result)

    output_file = Path(sys.argv[1]).stem + "_gemini.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Full JSON saved to: {output_file}")
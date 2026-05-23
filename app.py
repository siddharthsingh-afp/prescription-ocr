"""Prescription OCR - Single Upload."""

import json
import re
import time
from io import BytesIO
from pathlib import Path

from flask import Flask, request, jsonify, render_template
from PIL import Image, ImageFilter
from google import genai
from google.genai import types

app = Flask(__name__)
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}
MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".png": "image/png", ".webp": "image/webp"}


def assess_quality(image_bytes):
    # Simplified quality check without Pillow
    # Just return a default "good" rating for deployment
    return {"score": 75, "rating": "good", "message": "Quality check disabled for deployment"}


PROMPT = """Analyze this doctor's prescription from India. Extract as JSON:
- doctor_name, patient_name, date, diagnosis (if visible)
- medicines: list of {name, strength, form, dosage, frequency, duration, quantity, confidence (high/medium/low), notes}
- tests: list of {name, urgency, confidence, notes}
- warnings: list of strings

Rules: If unclear, set null + low confidence. Do NOT guess.
Return ONLY valid JSON, no markdown."""

client = genai.Client()


def extract(image_bytes, mime):
    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(r.text.strip())


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/quality", methods=["POST"])
def quality():
    if "image" not in request.files:
        return jsonify({"error": "No image"}), 400
    return jsonify(assess_quality(request.files["image"].read()))


@app.route("/extract", methods=["POST"])
def do_extract():
    if "image" not in request.files:
        return jsonify({"error": "No image"}), 400
    f = request.files["image"]
    suffix = Path(f.filename).suffix.lower()
    if suffix not in ALLOWED:
        return jsonify({"error": "Unsupported type"}), 400

    data_bytes = f.read()
    ts = int(time.time())
    (UPLOAD_FOLDER / f"{ts}_{f.filename}").write_bytes(data_bytes)

    try:
        result = extract(data_bytes, MIMES[suffix])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result["image_quality"] = assess_quality(data_bytes)
    for med in result.get("medicines", []):
        qty = str(med.get("quantity") or "")
        nums = re.findall(r"\d+", qty)
        med["quantity_value"] = int(nums[0]) if nums else 1

    (UPLOAD_FOLDER / f"{ts}_{Path(f.filename).stem}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify(result)

@app.route("/bulk")
def bulk_page():
    return render_template("bulk.html")


@app.route("/bulk/extract", methods=["POST"])
def bulk_extract():
    if "image" not in request.files:
        return jsonify({"error": "No image"}), 400
    f = request.files["image"]
    suffix = Path(f.filename).suffix.lower()
    if suffix not in ALLOWED:
        return jsonify({"error": "Unsupported type"}), 400

    data_bytes = f.read()
    ts = int(time.time() * 1000)
    (UPLOAD_FOLDER / f"bulk_{ts}_{f.filename}").write_bytes(data_bytes)

    q = assess_quality(data_bytes)
    if q["rating"] == "unusable":
        return jsonify({"image_quality": q, "medicines": [], "tests": [],
                        "warnings": ["Too blurry - skipped"]})
    try:
        result = extract(data_bytes, MIMES[suffix])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    result["image_quality"] = q
    return jsonify(result)

if __name__ == "__main__":
    print("=" * 60)
    print("Prescription OCR - Single Upload")
    print("Single:  http://localhost:5000")
    print("Bulk:    http://localhost:5000/bulk")
    print("Press Ctrl+C to stop.")
    print("=" * 60)
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
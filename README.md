# Prescription OCR — Enhanced Version

This version adds:
- **Image quality / blurriness scoring** — checked before OCR runs
- **Medicines AND lab tests** extraction (Gemini separates them)
- **Hospital inventory matching** — every extracted item fuzzy-matched to your inventory
- **Editable medicines** — +/− quantity, edit name/strength/frequency, pick alternatives, remove
- **Two pages** — single upload (port 5000), bulk upload (port 5001)
- **Audit logging** — every upload + extraction saved to `uploads/` folder

## Files

| File | What it does |
|---|---|
| `app.py` | Single-upload web app (port 5000) — main UI |
| `app_bulk.py` | Bulk-upload web app (port 5001) — process many at once |
| `make_sample_inventory.py` | Generates `hospital_inventory.csv` with sample data |
| `hospital_inventory.csv` | 128 sample medicines + 50 lab tests (generated) |

## One-time setup

You already have Python, Flask, and google-genai installed. You also need Pillow (for image quality):

```
python -m pip install pillow
```

That's the only new library.

## How to run

### Step 1: Generate the sample inventory (one time only)

```
python make_sample_inventory.py
```

This creates `hospital_inventory.csv` with 128 realistic Indian medicines and 50 lab tests.

When your real hospital inventory file arrives, replace this CSV with the same column structure and restart the apps.

### Step 2: Run the single-upload app

In one PowerShell window:

```
python app.py
```

Open browser: **http://localhost:5000**

### Step 3: (Optional) Run the bulk-upload app in a SEPARATE PowerShell window

Open a second PowerShell window (Windows key → powershell → Enter), navigate to the folder:

```
cd Desktop\prescription-ocr
python app_bulk.py
```

Open browser: **http://localhost:5001**

You can run both at the same time. Each one in its own PowerShell window.

## What you'll see

**Single upload (port 5000):**
1. Drag/click to upload prescription
2. Image quality bar appears (0-100 score with rating)
3. If quality is "unusable," extraction is blocked — user must retake
4. Click "Extract from Prescription" → 10-30s Gemini call
5. Right panel shows:
   - Doctor / patient / date / diagnosis
   - Each medicine with:
     - Green/yellow/red border (inventory match confidence)
     - Editable name, strength, frequency, duration, form
     - +/− quantity buttons
     - "Alternatives" link if uncertain match
     - "×" button to remove
     - Schedule H/H1 badge for prescription-only drugs
   - Each test with similar inventory matching
   - "+ Add medicine/test not detected" buttons
   - Final action: "Download JSON" or "Confirm Selection"

**Bulk upload (port 5001):**
1. Pick or drag many files at once
2. Click "Start Processing"
3. Progress bar shows current file (1 of N)
4. Live table fills in as each file completes
5. Stats: files processed, total medicines, % matched to inventory
6. "Download Summary CSV" gives Excel-ready file

## How inventory matching works

Each extracted medicine name goes through a fuzzy-matching function that:
1. Compares against every brand name + generic name in inventory
2. Boosts matches where the strength also matches
3. Returns confidence: `exact`, `high`, `medium`, `low`, or `none`

Test results from sample inventory:
- `'Flucan'` + `400mg` → **exact** → Flucan
- `'Flucam'` (OCR typo) → **high** → Flucan (87% similar)
- `'Augementin'` (OCR typo) → **exact** → Augmentin (96% similar)
- `'Xyzkitten'` (garbage) → **none** → flagged for pharmacist

## When real hospital inventory arrives

Replace `hospital_inventory.csv` with a file having these columns:

```
sku_id, item_type, brand_name, generic_name, strength, form, schedule, pack_size, mrp, hospital_id
```

- `item_type` = `medicine` or `test`
- `schedule` for medicines = `H`, `H1`, `X`, `G`, or `OTC`

Restart `app.py` and `app_bulk.py` to load the new inventory.

## Notes

- Uploaded images and JSON extractions are saved to `uploads/` for audit
- Bulk session summary stays in memory until you restart `app_bulk.py`
- Schedule H drugs get a blue badge in the UI — pharmacist must verify these
- Patients still need human verification before any order ships

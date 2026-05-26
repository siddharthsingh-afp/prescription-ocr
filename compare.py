"""Prescription OCR Comparison - Gemini Flash vs Claude Sonnet."""

import base64
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from flask import Flask, request, jsonify, render_template_string
from google import genai
from google.genai import types

app = Flask(__name__)

UPLOAD_FOLDER = Path("uploads_compare")
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}
MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".png": "image/png", ".webp": "image/webp"}

PROMPT = """Analyze this doctor's prescription from India. Extract as JSON:
- doctor_name, patient_name, date, diagnosis (if visible)
- medicines: list of {name, strength, form, dosage, frequency, duration, quantity, confidence (high/medium/low), notes}
- tests: list of {name, urgency, confidence, notes}
- warnings: list of strings

Rules: If unclear, set null + low confidence. Do NOT guess.
Return ONLY valid JSON, no markdown."""

# Initialize clients with environment variables
gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def extract_gemini(image_bytes, mime):
    start = time.time()
    try:
        r = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime), PROMPT],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        elapsed = time.time() - start
        data = json.loads(r.text.strip())
        data["_meta"] = {"model": "gemini-2.5-flash", "elapsed": round(elapsed, 2)}
        return data
    except Exception as e:
        return {"error": str(e), "_meta": {"model": "gemini-2.5-flash", "elapsed": round(time.time() - start, 2)}}


def extract_claude(image_bytes, mime):
    start = time.time()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    try:
        message = claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )
        elapsed = time.time() - start
        text = message.content[0].text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"error": "Invalid JSON", "raw": text[:200]}
        data["_meta"] = {
            "model": "claude-sonnet-4-6",
            "elapsed": round(elapsed, 2),
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
        }
        return data
    except Exception as e:
        return {"error": str(e), "_meta": {"model": "claude-sonnet-4-6", "elapsed": round(time.time() - start, 2)}}


def completeness_score(data):
    if data.get("error"):
        return 0
    score = 0
    if data.get("doctor_name"): score += 15
    if data.get("patient_name"): score += 15
    if data.get("date"): score += 10
    if data.get("diagnosis"): score += 10
    meds = data.get("medicines") or []
    if meds:
        score += 30
        avg_fields = sum(
            sum(1 for f in ["name", "strength", "frequency", "duration"] if m.get(f))
            for m in meds
        ) / max(1, len(meds)) / 4
        score += int(20 * avg_fields)
    return min(100, score)


HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>OCR Comparison</title>
<style>
*{box-sizing:border-box}body{font-family:-apple-system,Arial;background:#f5f7fa;margin:0;padding:20px}
.container{max-width:1400px;margin:0 auto}h1{color:#2c3e50;margin:0 0 8px}
.card{background:white;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.08);margin-bottom:20px}
.upload-area{border:2px dashed #cbd5e0;border-radius:8px;padding:40px 20px;text-align:center;cursor:pointer;background:#fafbfc}
.upload-area:hover{border-color:#4a90e2;background:#f0f7ff}
input[type="file"]{display:none}
button{background:#4a90e2;color:white;border:none;padding:12px 24px;border-radius:6px;font-size:14px;cursor:pointer;font-weight:500}
button:hover{background:#357abd}button:disabled{background:#adb5bd;cursor:not-allowed}
.preview{margin:16px 0;text-align:center}.preview img{max-width:400px;max-height:300px;border-radius:6px;border:1px solid #e2e8f0}
.status{margin:12px 0;padding:10px 14px;border-radius:6px;font-size:14px}
.status.loading{background:#fff8e1;color:#8a6d3b}.status.success{background:#e8f5e9;color:#2e7d32}
.status.error{background:#ffebee;color:#c62828}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:16px}
th{background:#f8f9fa;padding:12px 10px;text-align:left;font-weight:600;color:#495057;border-bottom:2px solid #e2e8f0}
td{padding:10px;border-bottom:1px solid #f0f0f0;vertical-align:top}
.label-col{background:#fafbfc;font-weight:600;color:#495057;width:160px}
.model-header{font-size:15px;font-weight:700;padding:8px 12px;border-radius:6px;margin-bottom:4px;display:inline-block}
.model-header.gemini{background:#e3f2fd;color:#1565c0}.model-header.claude{background:#f3e5f5;color:#6a1b9a}
.winner-badge{background:gold;color:#333;padding:4px 10px;border-radius:12px;font-size:11px;font-weight:700;margin-left:6px}
.score-pill{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;margin-left:6px}
.score-pill.high{background:#c8e6c9;color:#1b5e20}.score-pill.mid{background:#fff9c4;color:#827717}.score-pill.low{background:#ffcdd2;color:#b71c1c}
.time-pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#e9ecef;color:#495057;margin-left:4px}
.med-item{padding:6px 0;border-bottom:1px dashed #e9ecef}.med-item:last-child{border-bottom:none}
.med-name{font-weight:600;color:#2c3e50}.med-detail{font-size:11px;color:#6c757d;margin-top:2px}
.conf-badge{display:inline-block;padding:1px 6px;border-radius:8px;font-size:9px;font-weight:600;text-transform:uppercase;margin-left:4px}
.conf-badge.high{background:#d4edda;color:#155724}.conf-badge.medium{background:#fff3cd;color:#856404}.conf-badge.low{background:#f8d7da;color:#721c24}
.empty{color:#adb5bd;font-style:italic}
.actions{margin-top:16px;display:flex;gap:10px}.actions button.secondary{background:#6c757d}
.summary-row td{background:#f1f8ff;font-weight:600}.error-cell{color:#c62828;font-size:12px;font-style:italic}
</style></head><body>
<div class="container"><h1>OCR Comparison Tool</h1>
<p style="color:#6c757d;margin-bottom:24px;font-size:14px">Upload one prescription. Compare Gemini Flash vs Claude Sonnet side-by-side.</p>
<div class="card"><div id="uploadArea" class="upload-area">
<p><strong>Click to choose</strong> or drag a prescription image</p>
<p style="font-size:12px;color:#6c757d">JPG, PNG, WEBP</p>
<input type="file" id="fileInput" accept=".jpg,.jpeg,.png,.webp"></div>
<div id="preview" class="preview"></div><div id="status"></div>
<button id="compareBtn" style="display:none">Run Comparison</button></div>
<div id="results" style="display:none"></div></div>
<script>
const ua=document.getElementById('uploadArea'),fi=document.getElementById('fileInput'),
preview=document.getElementById('preview'),status=document.getElementById('status'),
compareBtn=document.getElementById('compareBtn'),results=document.getElementById('results');
let selectedFile=null,lastResults=null;
ua.addEventListener('click',()=>fi.click());
fi.addEventListener('change',e=>handleFile(e.target.files[0]));
ua.addEventListener('dragover',e=>{e.preventDefault();ua.classList.add('dragover')});
ua.addEventListener('dragleave',()=>ua.classList.remove('dragover'));
ua.addEventListener('drop',e=>{e.preventDefault();ua.classList.remove('dragover');
if(e.dataTransfer.files[0])handleFile(e.dataTransfer.files[0])});
function handleFile(file){if(!file)return;selectedFile=file;
const r=new FileReader();r.onload=e=>preview.innerHTML='<img src="'+e.target.result+'">';
r.readAsDataURL(file);status.innerHTML='<div class="status success">Loaded: '+file.name+' ('+(file.size/1024).toFixed(1)+' KB)</div>';
compareBtn.style.display='inline-block';results.style.display='none'}
compareBtn.addEventListener('click',async()=>{if(!selectedFile)return;compareBtn.disabled=true;
status.innerHTML='<div class="status loading">Running both models in parallel... 10-30 seconds.</div>';
results.style.display='none';const fd=new FormData();fd.append('image',selectedFile);
try{const t0=Date.now(),r=await fetch('/compare',{method:'POST',body:fd}),data=await r.json(),
elapsed=((Date.now()-t0)/1000).toFixed(1);if(data.error)status.innerHTML='<div class="status error">'+data.error+'</div>';
else{status.innerHTML='<div class="status success">Done in '+elapsed+'s</div>';lastResults=data;renderResults(data)}}
catch(e){status.innerHTML='<div class="status error">Error: '+e.message+'</div>'}
finally{compareBtn.disabled=false}});
function renderResults(data){const gemini=data.gemini||{},claude=data.claude||{},
winner=data.scores.claude>data.scores.gemini?'claude':data.scores.gemini>data.scores.claude?'gemini':'tie';
let html='<div class="card"><h2 style="margin-top:0">Comparison Results</h2><table><tr><th class="label-col">Field</th>';
html+=renderHeader('gemini','Gemini Flash',data.scores.gemini,gemini._meta,winner==='gemini');
html+=renderHeader('claude','Claude Sonnet',data.scores.claude,claude._meta,winner==='claude');
html+='</tr>';if(gemini.error||claude.error){html+='<tr><td class="label-col">Status</td>';
html+='<td>'+(gemini.error?'<span class="error-cell">ERROR: '+esc(gemini.error)+'</span>':'✓ Success')+'</td>';
html+='<td>'+(claude.error?'<span class="error-cell">ERROR: '+esc(claude.error)+'</span>':'✓ Success')+'</td></tr>'}
html+=renderRow('Doctor',gemini.doctor_name,claude.doctor_name);
html+=renderRow('Patient',gemini.patient_name,claude.patient_name);
html+=renderRow('Date',gemini.date,claude.date);
html+=renderRow('Diagnosis',gemini.diagnosis,claude.diagnosis);
html+='<tr><td class="label-col">Medicines</td><td>'+renderMeds(gemini.medicines)+'</td><td>'+renderMeds(claude.medicines)+'</td></tr>';
html+='<tr><td class="label-col">Tests</td><td>'+renderTests(gemini.tests)+'</td><td>'+renderTests(claude.tests)+'</td></tr>';
html+='<tr class="summary-row"><td class="label-col">Summary</td>';
html+='<td>'+(gemini.medicines||[]).length+' meds · '+(gemini.tests||[]).length+' tests</td>';
html+='<td>'+(claude.medicines||[]).length+' meds · '+(claude.tests||[]).length+' tests</td></tr></table>';
html+='<div class="actions"><button class="secondary" onclick="downloadJSON()">Download Full JSON</button></div></div>';
results.innerHTML=html;results.style.display='block'}
function renderHeader(cls,label,score,meta,isWinner){
const scoreCls=score>=70?'high':score>=40?'mid':'low';
return'<th style="width:50%"><div class="model-header '+cls+'">'+label+(isWinner?' <span class="winner-badge">🏆 WINNER</span>':'')+
'</div><div style="margin-top:4px"><span class="score-pill '+scoreCls+'">'+score+'/100</span>'+
'<span class="time-pill">'+(meta?.elapsed||'?')+'s</span></div></th>'}
function renderRow(label,g,c){const cell=v=>v?esc(v):'<span class="empty">—</span>';
return'<tr><td class="label-col">'+label+'</td><td>'+cell(g)+'</td><td>'+cell(c)+'</td></tr>'}
function renderMeds(meds){if(!meds||meds.length===0)return'<span class="empty">No medicines detected</span>';
return meds.map(m=>{const conf=(m.confidence||'low').toLowerCase(),
details=[m.strength,m.frequency,m.duration].filter(Boolean).join(' · ');
return'<div class="med-item"><span class="med-name">'+esc(m.name||'?')+'</span>'+
'<span class="conf-badge '+conf+'">'+conf+'</span>'+
(details?'<div class="med-detail">'+esc(details)+'</div>':'')+
(m.quantity?'<div class="med-detail">Qty: '+esc(m.quantity)+'</div>':'')+'</div>'}).join('')}
function renderTests(tests){if(!tests||tests.length===0)return'<span class="empty">No tests detected</span>';
return tests.map(t=>{const conf=(t.confidence||'low').toLowerCase();
return'<div class="med-item"><span class="med-name">'+esc(t.name||'?')+'</span>'+
'<span class="conf-badge '+conf+'">'+conf+'</span>'+
(t.urgency?'<div class="med-detail">Urgency: '+esc(t.urgency)+'</div>':'')+'</div>'}).join('')}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function downloadJSON(){const b=new Blob([JSON.stringify(lastResults,null,2)],{type:'application/json'}),
a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='comparison.json';a.click()}
</script></body></html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/compare", methods=["POST"])
def compare():
    if "image" not in request.files:
        return jsonify({"error": "No image"}), 400
    f = request.files["image"]
    suffix = Path(f.filename).suffix.lower()
    if suffix not in ALLOWED:
        return jsonify({"error": "Unsupported file type"}), 400

    image_bytes = f.read()
    mime = MIMES[suffix]

    ts = int(time.time())
    (UPLOAD_FOLDER / f"{ts}_{f.filename}").write_bytes(image_bytes)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_gemini = executor.submit(extract_gemini, image_bytes, mime)
        f_claude = executor.submit(extract_claude, image_bytes, mime)
        gemini_result = f_gemini.result()
        claude_result = f_claude.result()

    response = {
        "gemini": gemini_result,
        "claude": claude_result,
        "scores": {
            "gemini": completeness_score(gemini_result),
            "claude": completeness_score(claude_result),
        }
    }

    (UPLOAD_FOLDER / f"{ts}_{Path(f.filename).stem}_comparison.json").write_text(
        json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")

    return jsonify(response)


if __name__ == "__main__":
    print("=" * 60)
    print("OCR Comparison - Gemini Flash vs Claude Sonnet")
    print("=" * 60)
    print()
    print("Open: http://localhost:5002")
    print()
    print("Press Ctrl+C to stop.")
    print("=" * 60)
    app.run(debug=False, host="127.0.0.1", port=5002)
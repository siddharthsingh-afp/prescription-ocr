"""Prescription OCR - Bulk Upload (no inventory)."""

import csv
import json
import time
from io import StringIO
from pathlib import Path

from flask import Flask, request, jsonify, render_template_string, Response
from app import (assess_image_quality, extract_with_gemini,
                 MIME_TYPES, ALLOWED_EXTENSIONS, UPLOAD_FOLDER)

bulk_app = Flask(__name__)
SESSION_RESULTS = []


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Prescription OCR - Bulk</title>
<style>
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial;
       background: #f5f7fa; margin: 0; padding: 20px; color: #1a1a1a; }
.container { max-width: 1400px; margin: 0 auto; }
.topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
h1 { color: #2c3e50; margin: 0; }
.nav a { margin-left: 16px; color: #4a90e2; text-decoration: none; font-weight: 500; }
.nav a.active { color: #1a1a1a; pointer-events: none; }
.subtitle { color: #6c757d; margin-bottom: 24px; }
.card { background: white; border-radius: 12px; padding: 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 20px; }
.upload-area { border: 2px dashed #cbd5e0; border-radius: 8px; padding: 50px 20px;
               text-align: center; cursor: pointer; background: #fafbfc; }
.upload-area:hover { border-color: #4a90e2; background: #f0f7ff; }
.upload-area.dragover { border-color: #4a90e2; background: #e3f2fd; }
.icon { font-size: 48px; margin-bottom: 12px; }
input[type="file"] { display: none; }
button { background: #4a90e2; color: white; border: none; padding: 10px 20px;
         border-radius: 6px; font-size: 14px; cursor: pointer; font-weight: 500; }
button:hover { background: #357abd; }
button:disabled { background: #adb5bd; cursor: not-allowed; }
button.secondary { background: #6c757d; }
.progress { margin: 16px 0; padding: 12px 16px; border-radius: 6px;
            background: #fff8e1; color: #8a6d3b; font-size: 14px; }
.progress-bar { height: 8px; background: #e9ecef; border-radius: 4px;
                overflow: hidden; margin-top: 8px; }
.progress-fill { height: 100%; background: #4a90e2; }
.file-list { list-style: none; padding: 0; margin: 16px 0; max-height: 200px; overflow-y: auto; }
.file-list li { display: flex; justify-content: space-between; align-items: center;
                padding: 6px 10px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.file-list .status-pending { color: #6c757d; }
.file-list .status-processing { color: #ffc107; }
.file-list .status-done { color: #28a745; }
.file-list .status-error { color: #dc3545; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #f8f9fa; padding: 10px; text-align: left; font-weight: 600;
     color: #495057; border-bottom: 2px solid #e2e8f0; position: sticky; top: 0; }
td { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
tr:hover { background: #fafbfc; }
.badge { display: inline-block; padding: 1px 7px; border-radius: 10px;
         font-size: 10px; font-weight: 600; text-transform: uppercase; margin-right: 2px; }
.badge.high { background: #d4edda; color: #155724; }
.badge.medium { background: #fff3cd; color: #856404; }
.badge.low { background: #f8d7da; color: #721c24; }
.badge.quality-excellent, .badge.quality-good { background: #d4edda; color: #155724; }
.badge.quality-fair { background: #fff3cd; color: #856404; }
.badge.quality-poor, .badge.quality-unusable { background: #f8d7da; color: #721c24; }
.empty { color: #adb5bd; text-align: center; padding: 60px 20px; }
.stats { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.stat { background: #f8f9fa; padding: 10px 16px; border-radius: 8px; flex: 1; min-width: 140px; }
.stat .num { font-size: 22px; font-weight: 700; color: #2c3e50; }
.stat .lbl { font-size: 11px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.5px; }
.table-wrap { max-height: 600px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 8px; }
.med-row { font-size: 12px; padding: 2px 0; }
.med-row .name { font-weight: 500; }
.actions { display: flex; gap: 10px; margin-top: 16px; }
</style>
</head>
<body>
<div class="container">
  <div class="topbar">
    <h1>Prescription OCR - Bulk</h1>
    <div class="nav">
      <a href="http://localhost:5000">Single Upload</a>
      <a class="active">Bulk Upload</a>
    </div>
  </div>
  <p class="subtitle">Upload multiple prescriptions at once. Each is quality-checked and extracted.</p>
  <div class="card">
    <div id="uploadArea" class="upload-area">
      <div class="icon">[ + ]</div>
      <p><strong>Click to choose</strong> or drag &amp; drop multiple files</p>
      <p style="font-size:12px; color:#6c757d;">JPG/PNG/WEBP, many at once</p>
      <input type="file" id="fileInput" accept=".jpg,.jpeg,.png,.webp" multiple>
    </div>
    <ul id="fileList" class="file-list"></ul>
    <div id="progress" style="display:none"></div>
    <div class="actions">
      <button id="startBtn" disabled>Start Processing</button>
      <button id="clearBtn" class="secondary" style="display:none">Clear</button>
      <button id="downloadBtn" class="secondary" style="display:none">Download Summary CSV</button>
    </div>
  </div>
  <div class="card">
    <h3 style="margin-top:0">Results</h3>
    <div id="results"><div class="empty">No results yet. Upload files above and click Start.</div></div>
  </div>
</div>
<script>
const uploadArea=document.getElementById('uploadArea'),fileInput=document.getElementById('fileInput'),
fileList=document.getElementById('fileList'),startBtn=document.getElementById('startBtn'),
clearBtn=document.getElementById('clearBtn'),downloadBtn=document.getElementById('downloadBtn'),
progress=document.getElementById('progress'),resultsDiv=document.getElementById('results');
let pendingFiles=[],results=[];

uploadArea.addEventListener('click',()=>fileInput.click());
fileInput.addEventListener('change',e=>addFiles(Array.from(e.target.files)));
uploadArea.addEventListener('dragover',e=>{e.preventDefault();uploadArea.classList.add('dragover');});
uploadArea.addEventListener('dragleave',()=>uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop',e=>{e.preventDefault();uploadArea.classList.remove('dragover');
  addFiles(Array.from(e.dataTransfer.files));});

function addFiles(files){
  files=files.filter(f=>/\\.(jpe?g|png|webp)$/i.test(f.name));
  pendingFiles=pendingFiles.concat(files);
  renderFileList();startBtn.disabled=pendingFiles.length===0;
}

function renderFileList(){
  fileList.innerHTML='';
  pendingFiles.forEach(f=>{
    const li=document.createElement('li');
    li.innerHTML=`<span>${f.name} <span style="color:#adb5bd">(${(f.size/1024).toFixed(1)} KB)</span></span>
      <span class="status-${f.status||'pending'}">${f.status||'pending'}</span>`;
    fileList.appendChild(li);
  });
}

startBtn.addEventListener('click',async()=>{
  startBtn.disabled=true;results=[];
  resultsDiv.innerHTML='<div class="empty">Processing...</div>';
  progress.style.display='block';
  for(let i=0;i<pendingFiles.length;i++){
    const f=pendingFiles[i];f.status='processing';renderFileList();
    progress.innerHTML=`Processing ${i+1} of ${pendingFiles.length}: ${f.name}
      <div class="progress-bar"><div class="progress-fill" style="width:${(i/pendingFiles.length)*100}%"></div></div>`;
    try{
      const fd=new FormData();fd.append('image',f);
      const t0=Date.now();
      const r=await fetch('/extract',{method:'POST',body:fd});
      const data=await r.json();
      const elapsed=((Date.now()-t0)/1000).toFixed(1);
      if(data.error){f.status='error';results.push({filename:f.name,error:data.error,elapsed});}
      else{f.status='done';results.push({filename:f.name,data,elapsed});}
    }catch(err){f.status='error';results.push({filename:f.name,error:err.message,elapsed:'?'});}
    renderFileList();renderResults();
  }
  progress.innerHTML=`Done - processed ${pendingFiles.length} file(s).
    <div class="progress-bar"><div class="progress-fill" style="width:100%"></div></div>`;
  startBtn.disabled=false;clearBtn.style.display='inline-block';downloadBtn.style.display='inline-block';
});

clearBtn.addEventListener('click',()=>{
  pendingFiles=[];results=[];fileList.innerHTML='';
  resultsDiv.innerHTML='<div class="empty">No results yet.</div>';
  progress.style.display='none';clearBtn.style.display='none';downloadBtn.style.display='none';
  startBtn.disabled=true;
});

downloadBtn.addEventListener('click',()=>{
  fetch('/summary.csv').then(r=>r.blob()).then(blob=>{
    const a=document.createElement('a');a.href=URL.createObjectURL(blob);
    a.download='bulk_extraction_summary.csv';a.click();
  });
});

function renderResults(){
  if(results.length===0){resultsDiv.innerHTML='<div class="empty">No results yet.</div>';return;}
  const total=results.length,succeeded=results.filter(r=>!r.error).length,failed=total-succeeded;
  let totalMeds=0,totalTests=0;
  results.forEach(r=>{if(r.data){totalMeds+=(r.data.medicines||[]).length;
    totalTests+=(r.data.tests||[]).length;}});
  let html=`<div class="stats">
    <div class="stat"><div class="num">${total}</div><div class="lbl">Files</div></div>
    <div class="stat"><div class="num" style="color:${failed?'#dc3545':'#28a745'}">${succeeded}/${total}</div><div class="lbl">Succeeded</div></div>
    <div class="stat"><div class="num">${totalMeds}</div><div class="lbl">Total medicines</div></div>
    <div class="stat"><div class="num">${totalTests}</div><div class="lbl">Tests</div></div></div>`;
  html+='<div class="table-wrap"><table><thead><tr><th>File</th><th>Quality</th><th>Doctor/Patient</th><th>Medicines</th><th>Tests</th><th>Time</th></tr></thead><tbody>';
  for(const r of results){
    if(r.error){html+=`<tr><td>${r.filename}</td><td colspan="5" style="color:#dc3545;">Error: ${r.error}</td></tr>`;continue;}
    const d=r.data,q=d.image_quality||{},meds=d.medicines||[],tests=d.tests||[];
    html+=`<tr><td><strong>${r.filename}</strong></td>
      <td><span class="badge quality-${q.rating}">${q.rating||'?'}</span><br>
      <span style="font-size:11px;color:#6c757d">${q.score||0}/100</span></td>
      <td>${d.doctor_name||'<span style="color:#adb5bd">-</span>'}<br>
      <span style="color:#6c757d;font-size:11px">${d.patient_name||''} ${d.date?'- '+d.date:''}</span></td><td>`;
    if(meds.length===0)html+='<span style="color:#adb5bd">-</span>';
    else meds.forEach(m=>{const conf=(m.confidence||'low').toLowerCase();
      html+=`<div class="med-row"><span class="badge ${conf}">${conf}</span>
        <span class="name">${m.name||'?'}</span>
        ${m.strength?'<span style="color:#6c757d">'+m.strength+'</span>':''}</div>`;});
    html+='</td><td>';
    if(tests.length===0)html+='<span style="color:#adb5bd">-</span>';
    else tests.forEach(t=>{const conf=(t.confidence||'low').toLowerCase();
      html+=`<div class="med-row"><span class="badge ${conf}">${conf}</span> ${t.name||'?'}</div>`;});
    html+=`</td><td>${r.elapsed}s</td></tr>`;
  }
  html+='</tbody></table></div>';resultsDiv.innerHTML=html;
}
</script>
</body>
</html>
"""


@bulk_app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@bulk_app.route("/extract", methods=["POST"])
def extract():
    if "image" not in request.files:
        return jsonify({"error": "No image"}), 400
    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported type: {suffix}"}), 400

    image_bytes = file.read()
    timestamp = int(time.time() * 1000)
    save_path = UPLOAD_FOLDER / f"bulk_{timestamp}_{file.filename}"
    with open(save_path, "wb") as f:
        f.write(image_bytes)

    quality = assess_image_quality(image_bytes)
    if quality["rating"] == "unusable":
        result = {"image_quality": quality, "medicines": [], "tests": [],
                  "warnings": ["Image too blurry - skipped extraction"]}
    else:
        try:
            result = extract_with_gemini(image_bytes, MIME_TYPES[suffix])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        result["image_quality"] = quality

    SESSION_RESULTS.append({"filename": file.filename, "data": result})
    return jsonify(result)


@bulk_app.route("/summary.csv")
def summary_csv():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Filename", "Quality", "Score", "Doctor", "Patient", "Date", "Diagnosis",
                     "Type", "Name", "Strength", "Form", "Frequency", "Duration", "Quantity",
                     "Confidence", "Notes", "Warnings"])
    for entry in SESSION_RESULTS:
        d = entry["data"]
        q = d.get("image_quality", {})
        wstr = " | ".join(d.get("warnings", []))
        doctor, patient = d.get("doctor_name", ""), d.get("patient_name", "")
        date, diagnosis = d.get("date", ""), d.get("diagnosis", "")
        meds, tests = d.get("medicines", []), d.get("tests", [])
        if not meds and not tests:
            writer.writerow([entry["filename"], q.get("rating", ""), q.get("score", ""),
                            doctor, patient, date, diagnosis, "", "(nothing)",
                            "", "", "", "", "", "", "", wstr])
            continue
        first = True
        for m in meds:
            writer.writerow([entry["filename"] if first else "",
                q.get("rating", "") if first else "", q.get("score", "") if first else "",
                doctor if first else "", patient if first else "",
                date if first else "", diagnosis if first else "",
                "medicine", m.get("name", ""), m.get("strength", ""), m.get("form", ""),
                m.get("frequency", ""), m.get("duration", ""), m.get("quantity", ""),
                m.get("confidence", ""), m.get("notes", "") or "",
                wstr if first else ""])
            first = False
        for t in tests:
            writer.writerow([entry["filename"] if first else "",
                q.get("rating", "") if first else "", q.get("score", "") if first else "",
                doctor if first else "", patient if first else "",
                date if first else "", diagnosis if first else "",
                "test", t.get("name", ""), "", "", "", "", "",
                t.get("confidence", ""), t.get("notes", "") or "",
                wstr if first else ""])
            first = False
    return Response(output.getvalue(), mimetype="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=bulk_extraction_summary.csv"})


if __name__ == "__main__":
    print("=" * 60)
    print("Prescription OCR - Bulk Upload")
    print("=" * 60)
    print("\nOpen this URL in your browser:")
    print("  http://localhost:5001")
    print("\nNote: also start app.py separately (port 5000).")
    print("Press Ctrl+C to stop the server.")
    print("=" * 60)
    bulk_app.run(debug=False, host="127.0.0.1", port=5001)
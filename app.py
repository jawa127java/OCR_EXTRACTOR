from fastapi import FastAPI, UploadFile, File, HTTPException
import easyocr
import shutil
import tempfile
import os

from main2 import extract_mrz_line_1, extract_viz_data, verify_mrz_with_name

app = FastAPI(title="Passport Verification API")

# Initialize reader globally
reader = easyocr.Reader(['en', 'hi'], gpu=False)

@app.get("/")
def root():
    return {"status": "API is running"}

@app.post("/verify")
async def verify_passport(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    # Save uploaded file to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        ocr_results = reader.readtext(tmp_path)
        mrz_line = extract_mrz_line_1(ocr_results)
        viz_data = extract_viz_data(ocr_results)

        if not mrz_line:
            return {"error": "MRZ Line 1 not detected", "viz_data": viz_data}

        viz_surname = viz_data.get("surname") or ""
        viz_given_names = viz_data.get("given_names") or ""

        result = verify_mrz_with_name(mrz_line, viz_surname, viz_given_names)
        return {
            "mrz_line_1": mrz_line,
            "viz_data": viz_data,
            "verification": result
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

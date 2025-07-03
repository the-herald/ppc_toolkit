from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import sys
sys.path.append(os.path.dirname(__file__))

from cleaner import get_available_accounts, run_cleaner

app = FastAPI()

# === CORS (optional for GPT/Render use) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust if needed for security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Request Models ===
class ScanRequest(BaseModel):
    accounts: List[str]
    start_date: Optional[str] = None
    end_date: Optional[str] = None

class ApplyRequest(BaseModel):
    accounts: List[str]
    apply_indices: List[int]  # Indices of approved flagged terms

# === Routes ===
@app.get("/accounts")
def list_accounts():
    return get_available_accounts()

@app.post("/scan")
def scan_terms(req: ScanRequest):
    try:
        result = run_cleaner(
            selected_names=req.accounts,
            start_date=req.start_date,
            end_date=req.end_date,
            interactive=False
        )
        return {"status": "success", "results": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/apply")
def apply_terms(req: ApplyRequest):
    try:
        result = run_cleaner(
            selected_names=req.accounts,
            apply_indices=req.apply_indices,
            interactive=False
        )
        return {"status": "applied", "results": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

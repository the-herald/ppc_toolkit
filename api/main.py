import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "search_terms_cleaner")))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from cleaner import run_cleaner, get_available_accounts, AccountInfo

app = FastAPI()

# === Request models ===
class ScanRequest(BaseModel):
    account_names: List[str]
    start_date: Optional[str] = None  # YYYYMMDD
    end_date: Optional[str] = None    # YYYYMMDD

class ApplyRequest(BaseModel):
    account_name: str
    approved_indices: List[int]

# === Endpoints ===
@app.get("/accounts", response_model=List[AccountInfo])
def list_accounts():
    return get_available_accounts()

@app.post("/scan")
def scan_accounts(request: ScanRequest):
    return run_cleaner(
        selected_names=request.account_names,
        start_date=request.start_date,
        end_date=request.end_date,
        interactive=False
    )

@app.post("/apply")
def apply_approved(request: ApplyRequest):
    return run_cleaner(
        selected_names=[request.account_name],
        apply_indices=request.approved_indices,
        interactive=False
    )

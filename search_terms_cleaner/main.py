from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from cleaner import get_available_accounts, run_cleaner

app = FastAPI()

# Enable CORS for local testing and GPT interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Consider restricting in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/accounts")
def list_accounts():
    try:
        accounts = get_available_accounts()
        return {"accounts": accounts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run-cleaner")
def run_cleaner_endpoint(account_id: str = Query(..., description="Google Ads account ID")):
    try:
        result = run_cleaner(account_id)
        return {"message": "Cleaner finished successfully.", "results": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

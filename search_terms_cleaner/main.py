from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from cleaner import get_available_accounts, run_cleaner, ACCOUNT_MAP

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
        return {"accounts": list(ACCOUNT_MAP.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run-cleaner")
def run_cleaner_endpoint(account_input: str = Query(..., description="Account ID or name")):
    try:
        # Normalize input (handle short names, full names, or direct ID)
        account_id = None

        # Direct match by ID
        if account_input in ACCOUNT_MAP.values():
            account_id = account_input
        else:
            # Match by friendly name (case insensitive)
            for name, aid in ACCOUNT_MAP.items():
                if account_input.lower() in name.lower():
                    account_id = aid
                    break

        if not account_id:
            raise HTTPException(status_code=404, detail="Account not found.")

        result = run_cleaner(account_id)
        return {"message": f"Cleaner ran for account {account_id}", "results": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from cleaner import get_available_accounts, run_cleaner, ACCOUNT_MAP

app = FastAPI()

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
        return {
            "accounts": [
                {"name": name, "id": account_id}
                for name, account_id in ACCOUNT_MAP.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run-cleaner")
def run_cleaner_endpoint(account_input: str = Query(..., description="Comma-separated list of account names or IDs")):
    try:
        results = []
        inputs = [s.strip() for s in account_input.split(",")]

        for input_str in inputs:
            account_id = None

            if input_str in ACCOUNT_MAP.values():
                account_id = input_str
            else:
                for name, aid in ACCOUNT_MAP.items():
                    if input_str.lower() in name.lower():
                        account_id = aid
                        break

            if not account_id:
                results.append({
                    "input": input_str,
                    "error": "Account not found"
                })
                continue

            try:
                result = run_cleaner(account_id)
                results.append({
                    "account_id": account_id,
                    "input": input_str,
                    "message": f"Cleaner ran successfully for {input_str}",
                    "results": result
                })
            except Exception as e:
                results.append({
                    "account_id": account_id,
                    "input": input_str,
                    "error": str(e)
                })

        return {"scans": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

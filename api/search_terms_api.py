from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
import json
import os
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

app = FastAPI()

# === Load credentials and allowed accounts ===
with open("google_ads_token.json", "r") as f:
    token_data = json.load(f)

with open("client_secret.json", "r") as f:
    client_config = json.load(f)

with open("allowed_accounts.txt", "r") as f:
    allowed_accounts = [line.strip().replace("-", "") for line in f if line.strip()]

config = {
    "developer_token": "5dgO8PwWUCrkFzmgY1b_YA",
    "refresh_token": token_data["refresh_token"],
    "client_id": client_config["web"]["client_id"],
    "client_secret": client_config["web"]["client_secret"],
    "login_customer_id": "7297816540",
    "use_proto_plus": True,
}

client = GoogleAdsClient.load_from_dict(config)

# === Input model for POST requests ===
class ScanRequest(BaseModel):
    account_name: str
    max_days: Optional[int] = 7

# === Placeholder: Account name to ID mapping ===
account_name_to_id = {
    "Sound Concrete Solutions": "5616230554",
    "Woodlands Family Dental": "3035218698",
    # Add more as needed
}

# === Auto-disqualified root words ===
AUTO_EXCLUDE_TERMS = set([
    "cheap", "affordable", "diy",
    # add your full disqualifier list here if needed
])

# === Helper: Retrieve enabled campaigns ===
def get_search_campaigns(customer_id):
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.id, campaign.name
        FROM campaign
        WHERE campaign.status = 'ENABLED'
        AND campaign.advertising_channel_type = 'SEARCH'
    """
    return ga_service.search(customer_id=customer_id, query=query)

# === Helper: Retrieve search terms ===
def get_search_terms(customer_id, campaign_id, days):
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT search_term_view.search_term, metrics.clicks, metrics.conversions, ad_group_criterion.keyword.text
        FROM search_term_view
        WHERE campaign.id = {campaign_id}
        AND segments.date DURING LAST_{days}_DAYS
    """
    return ga_service.search(customer_id=customer_id, query=query)

# === API Route ===
@app.post("/scan-search-terms")
async def scan_search_terms(req: ScanRequest):
    account_id = account_name_to_id.get(req.account_name)
    if not account_id or account_id not in allowed_accounts:
        raise HTTPException(status_code=404, detail="Account not allowed or not found")

    auto_excluded = []
    flagged = []

    try:
        campaigns = get_search_campaigns(account_id)
        for row in campaigns:
            campaign_id = row.campaign.id
            campaign_name = row.campaign.name
            terms = get_search_terms(account_id, campaign_id, req.max_days)

            for result in terms:
                term = result.search_term_view.search_term.lower()
                keyword = result.ad_group_criterion.keyword.text.lower()
                clicks = result.metrics.clicks
                conversions = result.metrics.conversions

                # Check for auto-exclusion
                for word in AUTO_EXCLUDE_TERMS:
                    if word in term:
                        auto_excluded.append({
                            "term": term,
                            "reason": f"Contains disqualifier '{word}'",
                            "campaign": campaign_name
                        })
                        break
                else:
                    # Flag for manual review if suspicious (placeholder logic)
                    if conversions == 0 and clicks >= 3:
                        flagged.append({
                            "term": term,
                            "reason": f"Clicks with no conversions",
                            "campaign": campaign_name
                        })

        return {
            "account": req.account_name,
            "auto_excluded": auto_excluded,
            "flagged_for_review": flagged
        }

    except GoogleAdsException as ex:
        raise HTTPException(status_code=500, detail=str(ex))

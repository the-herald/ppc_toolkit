import os
import json
import logging
from typing import List, Dict
from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import openai

load_dotenv()

logging.basicConfig(level=logging.INFO)

DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize Google Ads client
client = GoogleAdsClient.load_from_storage("/etc/secrets/google-ads.yaml")

# === Dummy Account Map ===
ACCOUNT_MAP = {
    "First Doctors Weight Loss": "1462306408",
    "Four Seasons Residences Las Vegas": "1335938339",
}

# === Disqualifying Keywords ===
DISQUALIFIERS = [
    "cheap", "free", "affordable", "do it yourself", "jobs", "university",
    "wikipedia", "craigslist", "template", "sample", "how to", "salary",
    "career", "policy", "student", "definition", "internship"
]

# === Google Ads Query ===
SEARCH_TERM_QUERY = """
    SELECT
        search_term_view.search_term,
        campaign.id,
        ad_group.id
    FROM
        search_term_view
    WHERE
        segments.date DURING LAST_30_DAYS
        AND campaign.advertising_channel_type = 'SEARCH'
"""

# === AI Flagging ===
openai.api_key = OPENAI_API_KEY

def ai_flag_terms(terms: List[str]) -> List[Dict]:
    prompt = (
        "You are an expert in Google Ads. For each of the following search terms, decide if it's irrelevant or a competitor. "
        "Return results as JSON list with: search_term, flag_type ('irrelevant' or 'competitor'), and reason.\n\n"
        f"Search terms:\n{json.dumps(terms)}"
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You're an expert Google Ads analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        reply = response['choices'][0]['message']['content']
        return json.loads(reply)
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        return []

# === Cleaner Core ===
def get_available_accounts() -> List[str]:
    return list(ACCOUNT_MAP.values())

def run_cleaner(account_id: str) -> Dict:
    try:
        ga_service = client.get_service("GoogleAdsService")

        search_request = client.get_type("SearchGoogleAdsStreamRequest")
        search_request.customer_id = account_id
        search_request.query = SEARCH_TERM_QUERY

        response = ga_service.search_stream(request=search_request)

        flagged_terms = []
        auto_excluded = []

        for batch in response:
            for row in batch.results:
                term = row.search_term_view.search_term.lower()
                if any(d in term for d in DISQUALIFIERS):
                    auto_excluded.append({
                        "search_term": term,
                        "reason": "Contains disqualifying word"
                    })
                else:
                    flagged_terms.append(term)

        ai_results = ai_flag_terms(flagged_terms)

        return {
            "auto_excluded": auto_excluded,
            "flagged_by_ai": ai_results
        }

    except GoogleAdsException as ex:
        logging.error(f"Request failed: {ex}")
        raise

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

# === Load ENV VARS ===
DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === Real Account Map ===
ACCOUNT_MAP = {
    "Satilla Family Smiles (SFS) (Satilla)": "5616230554",  # SFS
    "First National Bank of Mount Dora (FNBMD) (First National)": "3035218698",  # FNBMD, First National
    "Gabaie & Associates (Gabaie)": "6666797635",  # Gabaie
    "Godley Station Dental (GSD) (Godley Station (or just Godley))": "6655601976",  # GSD, Godley Station, Godley
    "Three Ten Timber (Three Ten Timber)": "5692134970",  # Three Ten Timber
    "Four Seasons Residences Las Vegas (Four Seasons) (Four Seasons Residences)": "1335938339",  # Four Seasons
    "First Doctors Weight Loss (First Doctors)": "1462306408",  # First Doctors
    "BallparkDJ": "5287833435",
    "Andrew Casey Electrical Contractors (Andrew Casey)": "6807963143",  # Andrew Casey
    "Precise Home": "5392828629",
    "Dynamic Warehouse": "6309687513",
    "Rosco Generators": "3962597664",
    "Heart to Home Meals (Heart To Home) (H2H)": "2206893203",  # Heart To Home, H2H
    "UC Components": "3020635710",
    "CapioRN (Capio)": "3030064078",  # Capio
    "Iowa Countertops": "9552845701",
    "Action Engraving": "4224597425",
    "ScribbleVet": "6555309398",
    "Woodlands Family Dental (Woodlands)": "3466831668",  # Woodlands
    "Sound Concrete Solutions (Sound Concrete)": "3168167882",  # Sound Concrete
    "Bullet Proof Diesel (Bullet Proof)": "9162462492",  # Bullet Proof
    "Tristate Siding (Tristate)": "3229754921",  # Tristate
    "Sign Systems": "8343552815",
}

# === Disqualifiers ===
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

# === Initialize Google Ads Client ===
def get_client():
    return GoogleAdsClient.load_from_dict({
        "developer_token": DEVELOPER_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "login_customer_id": LOGIN_CUSTOMER_ID,
        "use_proto_plus": True
    })

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
        client = get_client()
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

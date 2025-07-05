import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from pydantic import BaseModel
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

# === Setup Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Constants ===
ACCOUNT_MAP: Dict[str, str] = {
    "Satilla Family Smiles (SFS)": "5616230554",
    "First National Bank of Mount Dora": "3035218698",
    "Gabaie & Associates": "6666797635",
    "Godley Station Dental (GSD)": "6655601976",
    "Three Ten Timber": "5692134970",
    "Four Seasons Residences Las Vegas": "1335938339",
    "First Doctors Weight Loss": "1462306408",
    "BallparkDJ": "5287833435",
    "Andrew Casey Electrical Contractors": "6807963143",
    "Precise Home": "5392828629",
    "Dynamic Warehouse": "6309687513",
    "Rosco Generators": "3962597664",
    "Heart To Home Meals": "2206893203",
    "Action Engraving": "4224597425",
    "ScribbleVet": "6555309398",
    "CapioRN": "3030064078",
    "Iowa Countertops": "9552845701",
    "Sound Concrete Solutions": "3168167882",
    "Bullet Proof Diesel": "9162462492",
    "Woodlands Family Dental": "3466831668",
    "UC Components": "3020635710",
    "Sign Systems": "8343552815",
    "Tristate Siding": "3229754921",
}

SHARED_LIST_NAME = "Low-quality Searches & Words"
COMPETITOR_LIST_NAME = "Competitor Terms"

AUTO_EXCLUDE_TERMS = set([
    "cheap", "affordable", "diy", "linkedin", "etsy", "free", "job", "tutorial",
    "university", "blog", "forum", "reddit", "youtube", "how to", "example", "course",
    "career", "classifieds", "school", "resume", "pet", "ebook", "amazon", "temu", "walmart"
])

# === Data Models ===
class AccountInfo(BaseModel):
    name: str
    id: str

class FlaggedTerm(BaseModel):
    search_term: str
    trouble_word: str
    reason: str
    is_competitor: bool

# === AI Flagging ===
def ai_flag_terms(terms: List[str], business_type: str = "general") -> List[Dict[str, str]]:
    prompt = f"""
You're helping manage Google Ads search terms for a business type: {business_type}.
Classify each term below as either:
- "irrelevant" (the user is not looking for our product/service),
- "competitor" (they mention another company or brand),
- or "safe" (the term is relevant or worth keeping).

Respond in JSON array format like:
[{{"term": "...", "type": "irrelevant" or "competitor", "reason": "why"}}]

Terms:
{terms}
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logging.error(f"AI filtering failed: {e}")
        return []

# === Google Ads Setup ===
def get_ads_client() -> GoogleAdsClient:
    dev_token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
    token_data = json.loads(os.getenv("GOOGLE_ADS_TOKEN"))
    with open(os.path.join(os.path.dirname(__file__), "client_secret.json")) as f:
        client_config = json.load(f)
    client_id = client_config.get("installed", {}).get("client_id") or client_config.get("web", {}).get("client_id")
    client_secret = client_config.get("installed", {}).get("client_secret") or client_config.get("web", {}).get("client_secret")
    config = {
        "developer_token": dev_token,
        "refresh_token": token_data["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
        "login_customer_id": "7297816540",
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(config)

# === Core Logic ===
def run_cleaner(selected_names: List[str], start_date: Optional[str] = None, end_date: Optional[str] = None,
                apply_indices: Optional[List[int]] = None, interactive: bool = True) -> List[Dict[str, Any]]:
    client = get_ads_client()
    today = datetime.today()
    start = start_date or (today - timedelta(days=29)).strftime("%Y%m%d")
    end = end_date or today.strftime("%Y%m%d")
    report = []

    for name in selected_names:
        acct_id = str(ACCOUNT_MAP.get(name))
        if not acct_id:
            report.append({"account": name, "error": "Account not found"})
            continue
        logger.info(f"🔍 Scanning account: {name} → {acct_id}")
        account_report = {"account": name, "flagged": [], "applied": []}
        try:
            all_terms = []
            for row in get_campaigns(client, acct_id):
                terms = get_search_terms(client, acct_id, row.campaign.id, start, end)
                all_terms.extend(terms)
            flagged = flag_terms(all_terms, business=name)
            account_report["flagged"] = flagged
            if not flagged:
                report.append(account_report)
                continue
            approved = flagged if not interactive else []
            if interactive:
                for i, t in enumerate(flagged, 1):
                    print(f"{i}. '{t.search_term}' ({t.reason})")
                sel = input("✅ Approve? (e.g. 1,3 or 'all'): ").strip().lower()
                if sel == "all":
                    approved = flagged
                else:
                    approved = [flagged[int(i)-1] for i in sel.split(",") if i.strip().isdigit()]
            competitors = [t for t in approved if t.is_competitor]
            general = [t for t in approved if not t.is_competitor]
            if general:
                sid = find_shared_list(client, acct_id, SHARED_LIST_NAME) or create_shared_list(client, acct_id, SHARED_LIST_NAME)
                add_negatives_to_list(client, acct_id, sid, general)
                account_report["applied"].extend(general)
            if competitors:
                cid = find_shared_list(client, acct_id, COMPETITOR_LIST_NAME)
                if cid:
                    add_negatives_to_list(client, acct_id, cid, competitors)
                    account_report["applied"].extend(competitors)
                else:
                    account_report["warning"] = "Competitor list not found"
        except GoogleAdsException as e:
            account_report["error"] = str(e)
        report.append(account_report)
    return report

# === Helpers ===
def flag_terms(terms: List[str], business: str) -> List[FlaggedTerm]:
    flagged = []
    for term in terms:
        term_lower = term.lower()
        for word in AUTO_EXCLUDE_TERMS:
            if word in term_lower:
                flagged.append(FlaggedTerm(search_term=term, trouble_word=word, reason=f"Matched disqualifier: {word}", is_competitor=False))
                break
    already_flagged = {f.search_term for f in flagged}
    ai_candidates = [t for t in terms if t not in already_flagged]
    ai_results = ai_flag_terms(ai_candidates, business_type=business)
    for r in ai_results:
        if r["type"] in ("irrelevant", "competitor"):
            flagged.append(FlaggedTerm(
                search_term=r["term"],
                trouble_word=r["term"].split()[0],
                reason=r["reason"],
                is_competitor=r["type"] == "competitor"
            ))
    return flagged

def get_campaigns(client: GoogleAdsClient, customer_id: str):
    query = """
        SELECT campaign.id, campaign.name
        FROM campaign
        WHERE campaign.status = 'ENABLED'
        AND campaign.advertising_channel_type = 'SEARCH'
    """
    return client.get_service("GoogleAdsService").search(customer_id=customer_id, query=query)

def get_search_terms(client: GoogleAdsClient, customer_id: str, campaign_id: int, start: str, end: str) -> List[str]:
    query = f"""
        SELECT search_term_view.search_term
        FROM search_term_view
        WHERE campaign.id = {campaign_id}
        AND segments.date BETWEEN '{start}' AND '{end}'
    """
    return [row.search_term_view.search_term for row in client.get_service("GoogleAdsService").search(customer_id=customer_id, query=query)]

def find_shared_list(client: GoogleAdsClient, customer_id: str, list_name: str) -> Optional[str]:
    query = f"""
        SELECT shared_set.id, shared_set.name
        FROM shared_set
        WHERE shared_set.name = '{list_name}'
        AND shared_set.type = 'NEGATIVE_KEYWORDS'
    """
    results = list(client.get_service("GoogleAdsService").search(customer_id=customer_id, query=query))
    return results[0].shared_set.id if results else None

def create_shared_list(client: GoogleAdsClient, customer_id: str, list_name: str) -> str:
    operation = client.get_type("SharedSetOperation")
    shared_set = operation.create
    shared_set.name = list_name
    shared_set.type = client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
    result = client.get_service("SharedSetService").mutate_shared_sets(customer_id=customer_id, operations=[operation])
    return result.results[0].resource_name.split("/")[-1]

def add_negatives_to_list(client: GoogleAdsClient, customer_id: str, list_id: str, terms: List[FlaggedTerm]):
    service = client.get_service("SharedCriterionService")
    operations = []
    seen = set()
    for t in terms:
        if not t.trouble_word or t.trouble_word.lower() in seen:
            continue
        seen.add(t.trouble_word.lower())
        op = client.get_type("SharedCriterionOperation")
        crit = op.create
        crit.shared_set = f"customers/{customer_id}/sharedSets/{list_id}"
        crit.keyword.text = t.trouble_word
        crit.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
        operations.append(op)
    if operations:
        service.mutate_shared_criteria(customer_id=customer_id, operations=operations)

import os
import json
from datetime import datetime, timedelta
from typing import List, Optional
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from pydantic import BaseModel

# === Constants ===
ACCOUNT_MAP = {
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

# === Pydantic Models ===
class AccountInfo(BaseModel):
    name: str
    id: str

class FlaggedTerm(BaseModel):
    search_term: str
    trouble_word: str
    reason: str
    is_competitor: bool

# === Google Ads Client Setup ===
def get_ads_client():
    google_ads_token = os.getenv("GOOGLE_ADS_TOKEN")
    if not google_ads_token:
        raise ValueError("Missing GOOGLE_ADS_TOKEN secret")

    token_data = json.loads(google_ads_token)

    with open(os.path.join(os.path.dirname(__file__), "client_secret.json")) as f:
        client_config = json.load(f)

    client_id = client_config.get("installed", {}).get("client_id") or client_config.get("web", {}).get("client_id")
    client_secret = client_config.get("installed", {}).get("client_secret") or client_config.get("web", {}).get("client_secret")

    config = {
        "developer_token": "5dgO8PwWUCrkFzmgY1b_YA",
        "refresh_token": token_data["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
        "login_customer_id": "7297816540",
        "use_proto_plus": True,
    }

    return GoogleAdsClient.load_from_dict(config)

client = get_ads_client()

# === Public helper ===
def get_available_accounts() -> List[AccountInfo]:
    return [AccountInfo(name=name, id=aid) for name, aid in ACCOUNT_MAP.items()]

# === Google Ads Helper Functions ===
def get_campaigns(customer_id: str):
    query = """
        SELECT campaign.id, campaign.name
        FROM campaign
        WHERE campaign.status = 'ENABLED'
        AND campaign.advertising_channel_type = 'SEARCH'
    """
    service = client.get_service("GoogleAdsService")
    return service.search(customer_id=customer_id, query=query)

def get_search_terms(customer_id: str, campaign_id: int, start: str, end: str) -> List[str]:
    query = f"""
        SELECT search_term_view.search_term
        FROM search_term_view
        WHERE campaign.id = {campaign_id}
        AND segments.date BETWEEN '{start}' AND '{end}'
    """
    service = client.get_service("GoogleAdsService")
    return [row.search_term_view.search_term for row in service.search(customer_id=customer_id, query=query)]

def flag_terms(terms: List[str]) -> List[FlaggedTerm]:
    flagged = []
    for term in terms:
        term_lower = term.lower()
        reason = None
        trouble_word = None

        for word in AUTO_EXCLUDE_TERMS:
            if word in term_lower:
                reason = f"Matched disqualifier: {word}"
                trouble_word = word
                break

        if not reason and any(w in term_lower for w in term_lower.split()):
            reason = "Suspected competitor term"
            trouble_word = term_lower.split()[0]

        if reason:
            flagged.append(FlaggedTerm(
                search_term=term,
                trouble_word=trouble_word,
                reason=reason,
                is_competitor="competitor" in reason.lower()
            ))
    return flagged

def find_shared_list(customer_id: str, list_name: str) -> Optional[str]:
    service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT shared_set.id, shared_set.name
        FROM shared_set
        WHERE shared_set.name = '{list_name}'
        AND shared_set.type = 'NEGATIVE_KEYWORDS'
    """
    results = list(service.search(customer_id=customer_id, query=query))
    return results[0].shared_set.id if results else None

def create_shared_list(customer_id: str, list_name: str) -> str:
    shared_set_service = client.get_service("SharedSetService")
    operation = client.get_type("SharedSetOperation")
    shared_set = operation.create
    shared_set.name = list_name
    shared_set.type = client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
    result = shared_set_service.mutate_shared_sets(customer_id=customer_id, operations=[operation])
    return result.results[0].resource_name.split("/")[-1]

def add_negatives_to_list(customer_id: str, list_id: str, terms: List[FlaggedTerm]):
    service = client.get_service("SharedCriterionService")
    operations = []

    for t in terms:
        for text in [t.search_term, t.trouble_word]:
            op = client.get_type("SharedCriterionOperation")
            crit = op.create
            crit.shared_set = f"customers/{customer_id}/sharedSets/{list_id}"
            crit.keyword.text = text
            crit.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
            operations.append(op)

    if operations:
        service.mutate_shared_criteria(customer_id=customer_id, operations=operations)

# === Core Cleaner Logic ===
def run_cleaner(
    selected_names: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    apply_indices: Optional[List[int]] = None,
    interactive: bool = True
):
    today = datetime.today()
    start = start_date or (today - timedelta(days=29)).strftime("%Y%m%d")
    end = end_date or today.strftime("%Y%m%d")

    report = []

    for name in selected_names:
        acct_id = ACCOUNT_MAP.get(name)
        if not acct_id:
            report.append({"account": name, "error": "Account not found"})
            continue

        account_report = {"account": name, "flagged": [], "applied": []}
        try:
            all_flagged = []
            campaigns = get_campaigns(acct_id)
            for row in campaigns:
                campaign_id = row.campaign.id
                terms = get_search_terms(acct_id, campaign_id, start, end)
                all_flagged.extend(flag_terms(terms))

            account_report["flagged"] = all_flagged

            if not all_flagged:
                report.append(account_report)
                continue

            if apply_indices is not None:
                approved = [all_flagged[i] for i in apply_indices if 0 <= i < len(all_flagged)]
            elif interactive:
                for i, term in enumerate(all_flagged, 1):
                    print(f"{i}. '{term.search_term}' ({term.reason})")
                sel = input("✅ Approve? (e.g. 1,3 or 'all'): ").strip().lower()
                approved = all_flagged if sel == "all" else [
                    all_flagged[int(i.strip()) - 1] for i in sel.split(",") if i.strip().isdigit()
                ]
            else:
                approved = []

            if not approved:
                report.append(account_report)
                continue

            competitors = [t for t in approved if t.is_competitor]
            general = [t for t in approved if not t.is_competitor]

            if general:
                sid = find_shared_list(acct_id, SHARED_LIST_NAME) or create_shared_list(acct_id, SHARED_LIST_NAME)
                add_negatives_to_list(acct_id, sid, general)
                account_report["applied"].extend(general)

            if competitors:
                cid = find_shared_list(acct_id, COMPETITOR_LIST_NAME)
                if cid:
                    add_negatives_to_list(acct_id, cid, competitors)
                    account_report["applied"].extend(competitors)
                else:
                    account_report["warning"] = "Competitor list not found"

        except GoogleAdsException as e:
            account_report["error"] = str(e)

        report.append(account_report)

    return report

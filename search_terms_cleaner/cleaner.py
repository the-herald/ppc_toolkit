# === cleaner.py ===

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

# === Disqualifiers ===
DISQUALIFIERS = [
    "cheap", "free", "affordable", "do it yourself", "jobs", "university",
    "wikipedia", "craigslist", "template", "sample", "how to", "salary",
    "career", "policy", "student", "definition", "internship"
]

# === Real Account Map ===
ACCOUNT_MAP = {
    # Format: alias (lowercased): account_id
    "satilla": "5616230554",
    "sfs": "5616230554",
    "satilla family smiles": "5616230554",

    "fnbmd": "3035218698",
    "first national": "3035218698",
    "first national bank of mount dora": "3035218698",

    "gabaie": "6666797635",
    "gabaie & associates": "6666797635",

    "godley": "6655601976",
    "godley station": "6655601976",
    "godley station dental": "6655601976",
    "gsd": "6655601976",

    "three ten": "5692134970",
    "three ten timber": "5692134970",

    "four seasons": "1335938339",
    "four seasons residences": "1335938339",
    "fsrlv": "1335938339",
    "four seasons las vegas": "1335938339",

    "first doctors": "1462306408",
    "fdwl": "1462306408",
    "first doctors weight loss": "1462306408",

    "ballparkdj": "5287833435",

    "andrew casey": "6807963143",
    "acec": "6807963143",
    "andrew casey electrical": "6807963143",

    "precise": "5392828629",
    "precise home": "5392828629",

    "dynamic": "6309687513",
    "dynamic warehouse": "6309687513",

    "rosco": "3962597664",
    "rosco generators": "3962597664",

    "h2h": "2206893203",
    "heart to home": "2206893203",
    "heart to home meals": "2206893203",
    "hthm": "2206893203",

    "uc": "3020635710",
    "uc components": "3020635710",

    "capio": "3030064078",
    "capiorn": "3030064078",

    "iowa": "9552845701",
    "iowa countertops": "9552845701",

    "action": "4224597425",
    "action engraving": "4224597425",

    "scribble": "6555309398",
    "scribblevet": "6555309398",

    "woodlands": "3466831668",
    "woodlands family dental": "3466831668",

    "sound concrete": "3168167882",
    "sound concrete solutions": "3168167882",

    "bpd": "9162462492",
    "bullet proof": "9162462492",
    "bullet proof diesel": "9162462492",

    "tristate": "3229754921",
    "tristate siding": "3229754921",

    "sign": "8343552815",
    "sign systems": "8343552815",
}

def get_available_accounts() -> List[str]:
    return list(ACCOUNT_MAP.values())

# === Setup ===
openai.api_key = OPENAI_API_KEY

def resolve_account_id(user_input: str) -> str:
    normalized = user_input.strip().lower()
    return ACCOUNT_MAP.get(normalized)

def get_client(account_id: str):
    return GoogleAdsClient.load_from_dict({
        "developer_token": DEVELOPER_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "login_customer_id": LOGIN_CUSTOMER_ID,
        "linked_customer_id": account_id,
        "use_proto_plus": True
    })


def ai_flag_terms(terms: List[str]) -> List[Dict]:
    prompt = (
        "You are an expert Google Ads analyst. For each search term, return a JSON object with: "
        "'search_term', 'flag_type' ('irrelevant', 'competitor', or 'none'), and 'reason'. "
        "Only return flagged terms."
        f"\n\nSearch terms:\n{json.dumps(terms)}"
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You're a senior-level Google Ads analyst. Only return flagged terms."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        reply = response['choices'][0]['message']['content']
        return json.loads(reply)
    except Exception as e:
        logging.error(f"[AI] Error flagging terms: {e}")
        return []


def apply_exclusions(client: GoogleAdsClient, account_id: str, flagged_terms: List[Dict]) -> Dict:
    try:
        neg_service = client.get_service("GoogleAdsService")
        campaign_service = client.get_service("CampaignService")
        shared_set_service = client.get_service("SharedSetService")
        shared_criterion_service = client.get_service("SharedCriterionService")

        irrelevant_terms = [t for t in flagged_terms if t['flag_type'] == 'irrelevant']
        competitor_terms = [t for t in flagged_terms if t['flag_type'] == 'competitor']

        shared_sets = {
            "irrelevant": "Low-quality Searches & Words",
            "competitor": "Competitor Terms"
        }

        def create_or_get_shared_set(name):
            query = f"""
            SELECT shared_set.id FROM shared_set
            WHERE shared_set.name = '{name}'
            LIMIT 1
            """
            response = neg_service.search(customer_id=account_id, query=query)
            for row in response:
                return row.shared_set.id
            # If not found, create
            operation = client.get_type("SharedSetOperation")
            shared_set = operation.create
            shared_set.name = name
            shared_set.type = client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
            result = shared_set_service.mutate_shared_sets(customer_id=account_id, operations=[operation])
            return result.results[0].resource_name.split("/")[-1]

        def deduplicate(shared_set_id: str, new_terms: List[str]):
            existing = set()
            query = f"SELECT shared_criterion.keyword.text FROM shared_criterion WHERE shared_set.id = {shared_set_id}"
            response = neg_service.search(customer_id=account_id, query=query)
            for row in response:
                existing.add(row.shared_criterion.keyword.text.lower())
            return [t for t in new_terms if t.lower() not in existing]

        result_log = {}

        for label, terms in [("irrelevant", irrelevant_terms), ("competitor", competitor_terms)]:
            if not terms:
                continue
            shared_set_id = create_or_get_shared_set(shared_sets[label])

            phrases = []
            for t in terms:
                phrases.append(t['search_term'])
                if label == 'irrelevant':
                    root = t['search_term'].split()[0]
                    phrases.append(root)
                elif label == 'competitor':
                    root = t['search_term'].split()[0]
                    phrases.append(root)

            unique_phrases = deduplicate(shared_set_id, phrases)
            if not unique_phrases:
                result_log[label] = "No new exclusions after deduplication."
                continue

            operations = []
            for phrase in unique_phrases:
                criterion = client.get_type("SharedCriterionOperation")
                criterion.create.keyword.text = phrase
                criterion.create.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
                criterion.create.shared_set = shared_set_service.shared_set_path(account_id, shared_set_id)
                operations.append(criterion)

            shared_criterion_service.mutate_shared_criteria(customer_id=account_id, operations=operations)
            result_log[label] = f"{len(unique_phrases)} exclusions applied."

        return result_log

    except Exception as e:
        logging.error(f"[EXCLUSION ERROR] {e}")
        return {"error": str(e)}


def run_cleaner(account_id: str) -> dict:
    logging.info(f"[Cleaner] Starting for account ID: {account_id}")
    client = get_client(account_id)

    try:
        ga_service = client.get_service("GoogleAdsService")

        query = """
        SELECT
            campaign.id,
            campaign.name,
            ad_group.id,
            search_term_view.search_term,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions
        FROM search_term_view
        WHERE segments.date DURING LAST_30_DAYS
          AND campaign.advertising_channel_type = 'SEARCH'
        """

        response = ga_service.search_stream(customer_id=account_id, query=query)

        search_terms = set()
        for batch in response:
            for row in batch.results:
                term = row.search_term_view.search_term
                if term:
                    search_terms.add(term)

        if not search_terms:
            logging.info(f"[Cleaner] No search term data for account: {account_id}")
            return {"status": "no_data", "account_id": account_id}

        # === Auto Exclude Disqualifiers ===
        auto_excluded = [term for term in search_terms if any(d in term.lower() for d in DISQUALIFIERS)]

        # === AI Review ===
        reviewable_terms = list(search_terms - set(auto_excluded))
        ai_flagged = ai_flag_terms(reviewable_terms)

        # === Apply auto exclusions only
        exclusion_result = apply_exclusions(client, account_id, [
            {"search_term": t, "flag_type": "irrelevant", "reason": "Matched disqualifier list"}
            for t in auto_excluded
        ])

        return {
            "status": "success",
            "account_id": account_id,
            "auto_excluded": auto_excluded,
            "ai_flagged": ai_flagged,
            "flagged_count": len(ai_flagged),
            "exclusion_result": exclusion_result
        }

    except GoogleAdsException as ex:
        logging.error(f"[GoogleAdsException] {ex.failure}")
        return {"status": "error", "account_id": account_id, "error": str(ex)}

    except Exception as e:
        logging.error(f"[Cleaner] General error for {account_id}: {e}")
        return {"status": "error", "account_id": account_id, "error": str(e)}

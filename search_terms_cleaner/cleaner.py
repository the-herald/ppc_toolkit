import os
import json
import logging
from typing import List, Dict
from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import openai

# === Load environment ===
load_dotenv()

# === Logging ===
logging.basicConfig(level=logging.INFO)

# === Env Variables ===
DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === OpenAI Config ===
openai.api_key = OPENAI_API_KEY

# === Disqualifiers List ===
DISQUALIFIERS = [
    "cheap", "free", "affordable", "do it yourself", "jobs", "university",
    "wikipedia", "craigslist", "template", "sample", "how to", "salary",
    "career", "policy", "student", "definition", "internship"
]

# === Account Map ===
ACCOUNT_MAP = {
    "first doctors": "1462306408", "fdwl": "1462306408",
    "four seasons": "1335938339", "fsrlv": "1335938339",
    "iowa": "9552845701", "iowa countertops": "9552845701",
    # [trimmed for brevity; insert full map from previous version]
}

def get_available_accounts() -> List[str]:
    return list(ACCOUNT_MAP.values())

def resolve_account_id(user_input: str) -> str:
    normalized = user_input.strip().lower()
    if normalized in ACCOUNT_MAP:
        return ACCOUNT_MAP[normalized]
    for alias, acct_id in ACCOUNT_MAP.items():
        if normalized in alias:
            return acct_id
    return None

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
        "Only return flagged terms.\n\nSearch terms:\n" + json.dumps(terms)
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You're a senior-level Google Ads analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        content = response['choices'][0]['message']['content']
        return json.loads(content)
    except Exception as e:
        logging.error(f"[AI] Error or JSON parsing issue: {e}")
        return []

def apply_exclusions(client, account_id: str, flagged_terms: List[Dict]) -> Dict:
    try:
        ga_service = client.get_service("GoogleAdsService")
        shared_set_service = client.get_service("SharedSetService")
        shared_criterion_service = client.get_service("SharedCriterionService")

        shared_sets = {
            "irrelevant": "Low-quality Searches & Words",
            "competitor": "Competitor Terms"
        }

        def create_or_get_shared_set(name):
            query = f"SELECT shared_set.id FROM shared_set WHERE shared_set.name = '{name}' LIMIT 1"
            response = ga_service.search(customer_id=account_id, query=query)
            for row in response:
                return row.shared_set.id
            operation = client.get_type("SharedSetOperation")()
            shared_set = operation.create
            shared_set.name = name
            shared_set.type = client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
            result = shared_set_service.mutate_shared_sets(customer_id=account_id, operations=[operation])
            return result.results[0].resource_name.split("/")[-1]

        def deduplicate(shared_set_id: str, new_terms: List[str]):
            existing = set()
            query = f"SELECT shared_criterion.keyword.text FROM shared_criterion WHERE shared_set.id = {shared_set_id}"
            response = ga_service.search(customer_id=account_id, query=query)
            for row in response:
                existing.add(row.shared_criterion.keyword.text.lower())
            return [t for t in new_terms if t.lower() not in existing]

        result_log = {}
        for label in ["irrelevant", "competitor"]:
            terms = [t for t in flagged_terms if t['flag_type'] == label]
            if not terms:
                continue
            shared_set_id = create_or_get_shared_set(shared_sets[label])
            phrases = []
            for t in terms:
                phrases.append(t['search_term'])
                phrases.append(t['search_term'].split()[0])  # Root word
            unique_phrases = deduplicate(shared_set_id, phrases)
            if not unique_phrases:
                result_log[label] = "No new exclusions."
                continue
            operations = []
            for phrase in unique_phrases:
                op = client.get_type("SharedCriterionOperation")()
                criterion = op.create
                criterion.keyword.text = phrase
                criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
                criterion.shared_set = shared_set_service.shared_set_path(account_id, shared_set_id)
                operations.append(op)
            shared_criterion_service.mutate_shared_criteria(customer_id=account_id, operations=operations)
            result_log[label] = f"{len(unique_phrases)} exclusions applied."
        return result_log
    except Exception as e:
        logging.error(f"[Exclusion Error] {e}")
        return {"error": str(e)}

def run_cleaner(account_id: str) -> Dict:
    logging.info(f"[Cleaner] Running for account: {account_id}")
    client = get_client(account_id)
    try:
        service = client.get_service("GoogleAdsService")
        query = """
            SELECT
              search_term_view.search_term,
              metrics.impressions,
              metrics.clicks,
              metrics.conversions
            FROM search_term_view
            WHERE segments.date DURING LAST_30_DAYS
              AND campaign.advertising_channel_type = 'SEARCH'
        """
        response = service.search(customer_id=str(account_id), query=query)
        search_terms = {row.search_term_view.search_term for row in response if row.search_term_view.search_term}

        if not search_terms:
            return {"status": "no_data", "account_id": account_id}

        auto_excluded = [t for t in search_terms if any(d in t.lower() for d in DISQUALIFIERS)]
        reviewable_terms = list(search_terms - set(auto_excluded))
        ai_flagged = ai_flag_terms(reviewable_terms)

        exclusions = [
            {"search_term": t, "flag_type": "irrelevant", "reason": "Matched disqualifier list"}
            for t in auto_excluded
        ] + [t for t in ai_flagged if t['flag_type'] in ('irrelevant', 'competitor')]

        exclusion_result = apply_exclusions(client, account_id, exclusions)

        return {
            "status": "success",
            "account_id": account_id,
            "auto_excluded": auto_excluded,
            "ai_flagged": ai_flagged,
            "flagged_count": len(ai_flagged),
            "exclusion_result": exclusion_result
        }

    except GoogleAdsException as e:
        logging.error(f"[GoogleAdsException] {e.failure}")
        return {"status": "error", "error": str(e), "account_id": account_id}
    except Exception as e:
        logging.error(f"[Cleaner Error] {e}")
        return {"status": "error", "error": str(e), "account_id": account_id}

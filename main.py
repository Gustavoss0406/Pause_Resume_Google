import logging
import json
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import aiohttp
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

API_VERSION     = "v17"
DEVELOPER_TOKEN = "D4yv61IQ8R0JaE5dxrd1Uw"
CLIENT_ID       = "167266694231-g7hvta57r99etbp3sos3jfi7q7h4ef44.apps.googleusercontent.com"
CLIENT_SECRET   = "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"

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_access_token(refresh_token: str) -> str:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    creds.refresh(GoogleRequest())
    return creds.token

async def find_customer_for_campaign(access_token: str, campaign_id: str) -> str:
    # ... idêntico ao seu código atual ...
    # retorna o customer_id onde a campanha vive
    # (mantém exactly o find_customer_for_campaign que você já tem)
    # …

async def get_campaign_status(customer_id: str, campaign_id: str, access_token: str) -> str:
    """
    Busca o status atual da campanha via googleAds:search.
    Retorna um dos: "ENABLED", "PAUSED", "REMOVED", etc.
    """
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers/{customer_id}/googleAds:search"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    query = (
        "SELECT campaign.status "
        f"FROM campaign "
        f"WHERE campaign.id = {campaign_id} "
        "LIMIT 1"
    )
    body = {"query": query}
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, headers=headers, json=body) as resp:
            text = await resp.text()
            logging.debug(f"[get_status] status={resp.status}, body={text}")
            if resp.status != 200:
                raise HTTPException(status_code=502, detail=f"Erro ao buscar status: {text}")
            data = json.loads(text)
            results = data.get("results", [])
            if not results:
                raise HTTPException(status_code=404, detail="Campanha não encontrada.")
            status = results[0]["campaign"]["status"]
            return status

async def mutate_campaign_status(customer_id: str, campaign_id: str, status: str, access_token: str):
    # ... idêntico ao seu current mutate_campaign_status …
    # usando campaigns:mutate com updateMask=status …
    # …

@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "É necessário 'refresh_token' e 'campaign_id'.")
    
    access_token = await get_access_token(refresh_token)
    customer_id  = await find_customer_for_campaign(access_token, campaign_id)

    # NOVO: busca status antes de mutar
    current_status = await get_campaign_status(customer_id, campaign_id, access_token)
    logging.debug(f"[resume] Campaign {campaign_id} current status: {current_status}")
    if current_status == "ENABLED":
        return {"success": False, "detail": "Campaign already enabled"}
    if current_status == "REMOVED":
        raise HTTPException(409, "Cannot resume: campaign is removed permanently.")
    if current_status != "PAUSED":
        raise HTTPException(409, f"Cannot resume: campaign status is {current_status} (expected PAUSED).")

    # só agora, de fato reativa
    result = await mutate_campaign_status(customer_id, campaign_id, "ENABLED", access_token)
    logging.info(f"[resume] Campaign {campaign_id} resumed in customer {customer_id}")
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id, "response": result}

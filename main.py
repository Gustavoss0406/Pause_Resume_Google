import logging
import json
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import aiohttp
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

# === Settings ===
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
        client_secret=CLIENT_SECRET,
    )
    creds.refresh(GoogleRequest())
    return creds.token

async def discover_customer_id(access_token: str) -> str:
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers:listAccessibleCustomers"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url, headers=headers) as resp:
            text = await resp.text()
            logging.debug(f"[discover] {resp.status} {text}")
            if resp.status != 200:
                raise HTTPException(502, f"listAccessibleCustomers error: {text}")
            names = json.loads(text).get("resourceNames", [])
            if not names:
                raise HTTPException(502, "No accessible customers")
            return names[0].split("/")[-1]

async def get_campaign_status(customer_id: str, campaign_id: str, access_token: str) -> str:
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
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, headers=headers, json={"query": query}) as resp:
            text = await resp.text()
            logging.debug(f"[get_status] {resp.status} {text}")
            if resp.status != 200:
                raise HTTPException(502, f"Status query error: {text}")
            results = json.loads(text).get("results", [])
            if not results:
                raise HTTPException(404, "Campaign not found")
            return results[0]["campaign"]["status"]

async def patch_campaign_status(customer_id: str, campaign_id: str, status: str, access_token: str):
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers/{customer_id}/campaigns/{campaign_id}"
    params = {"updateMask": "status"}
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    body = {"status": status}
    logging.debug(f"[patch] PATCH {url}?updateMask=status body={body}")
    async with aiohttp.ClientSession() as sess:
        async with sess.patch(url, params=params, headers=headers, json=body) as resp:
            text = await resp.text()
            logging.debug(f"[patch] {resp.status} {text}")
            if resp.status != 200:
                raise HTTPException(resp.status, f"Patch error: {text}")
            return json.loads(text)

@app.post("/pause_google_campaign")
async def pause_google_campaign(payload: dict = Body(...)):
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "Need 'refresh_token' and 'campaign_id'")
    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    # 1) pausar
    patch_resp = await patch_campaign_status(customer_id, campaign_id, "PAUSED", access_token)
    logging.debug(f"[pause] patch response: {patch_resp}")

    # 2) confirmar
    confirmed = await get_campaign_status(customer_id, campaign_id, access_token)
    logging.info(f"[pause] confirmed status: {confirmed}")
    if confirmed != "PAUSED":
        raise HTTPException(500, f"Failed to pause: status is {confirmed}")

    return {"success": True, "campaign_id": campaign_id, "confirmed_status": confirmed}

@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "Need 'refresh_token' and 'campaign_id'")
    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    # 1) reativar
    patch_resp = await patch_campaign_status(customer_id, campaign_id, "ENABLED", access_token)
    logging.debug(f"[resume] patch response: {patch_resp}")

    # 2) confirmar
    confirmed = await get_campaign_status(customer_id, campaign_id, access_token)
    logging.info(f"[resume] confirmed status: {confirmed}")
    if confirmed != "ENABLED":
        raise HTTPException(500, f"Failed to resume: status is {confirmed}")

    return {"success": True, "campaign_id": campaign_id, "confirmed_status": confirmed}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

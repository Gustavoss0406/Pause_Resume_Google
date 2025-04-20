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

# configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI()

# CORS – ajuste as origens se quiser restringir
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.adstock.ai", "https://pauseresumegoogle-production.up.railway.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_access_token(refresh_token: str) -> str:
    """Renova o access token a partir do refresh token."""
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
    """Chama customers:listAccessibleCustomers para descobrir o primeiro customer_id."""
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers:listAccessibleCustomers"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            logging.debug(f"[discover] status={resp.status}, body={text}")
            if resp.status != 200:
                raise HTTPException(status_code=502, detail=f"Erro ao listar contas: {text}")
            body = json.loads(text)
            names = body.get("resourceNames", [])
            if not names:
                raise HTTPException(status_code=502, detail="Nenhuma conta acessível encontrada.")
            # resourceNames: ["customers/1234567890", ...]
            return names[0].split("/")[-1]

async def mutate_campaign_status(customer_id: str, campaign_id: str, status: str, access_token: str):
    """Usa CampaignService.mutate para atualizar o status da campanha."""
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers/{customer_id}/campaigns:mutate"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    body = {
        "operations": [
            {
                "update": {
                    "resourceName": f"customers/{customer_id}/campaigns/{campaign_id}",
                    "status": status
                },
                "updateMask": "status"
            }
        ]
    }
    logging.debug(f"[mutate] POST {url} body={json.dumps(body)}")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body) as resp:
            text = await resp.text()
            logging.debug(f"[mutate] status={resp.status}, body={text}")
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail=text)
            return json.loads(text)

async def get_campaign_status(customer_id: str, campaign_id: str, access_token: str) -> str:
    """
    Busca o status atual da campanha via googleAds:search.
    Retorna o enum exato do Google Ads: ENABLED, PAUSED, REMOVED, etc.
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
    logging.debug(f"[get_status] POST {url} body={body}")
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
            return results[0]["campaign"]["status"]

@app.post("/pause_google_campaign")
async def pause_google_campaign(payload: dict = Body(...)):
    logging.debug(f"[pause] Payload: {json.dumps(payload)}")
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")

    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    # 1) Envia o mutate para PAUSED
    mutate_resp = await mutate_campaign_status(customer_id, campaign_id, "PAUSED", access_token)
    logging.info(f"[pause] Mutate response: {mutate_resp}")

    # 2) Confirma o status após o mutate
    new_status = await get_campaign_status(customer_id, campaign_id, access_token)
    logging.info(f"[pause] Campaign {campaign_id} new status: {new_status}")

    return {
        "success": True,
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "mutate_response": mutate_resp,
        "confirmed_status": new_status
    }

@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    logging.debug(f"[resume] Payload: {json.dumps(payload)}")
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")

    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    # Reativa usando ENABLED
    result = await mutate_campaign_status(customer_id, campaign_id, "ENABLED", access_token)
    logging.info(f"[resume] Campanha {campaign_id} reativada na conta {customer_id}")

    # Confirma status
    confirmed = await get_campaign_status(customer_id, campaign_id, access_token)
    logging.info(f"[resume] Campaign {campaign_id} confirmed status: {confirmed}")

    return {
        "success": True,
        "customer_id": customer_id,
        "campaign_id": campaign_id,
        "mutate_response": result,
        "confirmed_status": confirmed
    }

if __name__ == "__main__":
    import uvicorn
    logging.info("Iniciando FastAPI (Google Ads pause/resume) na porta 8080")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

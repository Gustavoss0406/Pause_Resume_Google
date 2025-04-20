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
    allow_origins=["https://app.adstock.ai", "https://pauseresumegoogle-production.up.railway.app"],
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
            return names[0].split("/")[-1]

async def google_ads_search(customer_id: str, access_token: str, query: str):
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers/{customer_id}/googleAds:search"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    body = {"query": query}
    logging.debug(f"[search] POST {url} body={body}")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body) as resp:
            text = await resp.text()
            logging.debug(f"[search] status={resp.status}, body={text}")
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail=text)
            return json.loads(text).get("results", [])

async def mutate_campaign_status(customer_id: str, campaign_id: str, status: str, access_token: str):
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

@app.post("/list_paused_google_campaigns")
async def list_paused_google_campaigns(payload: dict = Body(...)):
    """
    Lista todas as campanhas com status PAUSED.
    Body: { "refresh_token": "...", "customer_id": optional }
    """
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token'.")
    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    query = """
        SELECT
          campaign.id,
          campaign.name,
          campaign.status
        FROM campaign
        WHERE campaign.status = PAUSED
    """
    results = await google_ads_search(customer_id, access_token, query)
    # converte resultados em um formato simples
    paused = [
        {
            "id":      r["campaign"]["id"],
            "name":    r["campaign"]["name"],
            "status":  r["campaign"]["status"]
        }
        for r in results
    ]
    return {"customer_id": customer_id, "paused_campaigns": paused}

@app.post("/get_google_campaign_status")
async def get_google_campaign_status(payload: dict = Body(...)):
    """
    Recupera o status de uma campanha específica.
    Body: { "refresh_token": "...", "campaign_id": "...", "customer_id": optional }
    """
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")
    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    query = f"""
        SELECT
          campaign.id,
          campaign.status
        FROM campaign
        WHERE campaign.id = {campaign_id}
    """
    results = await google_ads_search(customer_id, access_token, query)
    if not results:
        raise HTTPException(status_code=404, detail="Campanha não encontrada.")
    status = results[0]["campaign"]["status"]
    return {"campaign_id": campaign_id, "status": status}

@app.post("/pause_google_campaign")
async def pause_google_campaign(payload: dict = Body(...)):
    logging.debug(f"[pause] Payload: {json.dumps(payload)}")
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")
    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)
    result = await mutate_campaign_status(customer_id, campaign_id, "PAUSED", access_token)
    logging.info(f"[pause] Campanha {campaign_id} pausada na conta {customer_id}")
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id, "response": result}

@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    logging.debug(f"[resume] Payload: {json.dumps(payload)}")
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")
    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    # verifica antes o status real
    status_resp = await get_google_campaign_status({
        "refresh_token": refresh_token,
        "campaign_id":   campaign_id,
        "customer_id":   customer_id
    })
    if status_resp["status"] == "REMOVED":
        raise HTTPException(status_code=409, detail="Essa campanha foi removida e não pode ser reativada.")
    if status_resp["status"] != "PAUSED":
        raise HTTPException(status_code=409, detail=f"Status atual é {status_resp['status']}, só PAUSED pode ser reativada.")

    # finalmente reativa
    result = await mutate_campaign_status(customer_id, campaign_id, "ENABLED", access_token)
    logging.info(f"[resume] Campanha {campaign_id} reativada na conta {customer_id}")
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id, "response": result}

if __name__ == "__main__":
    import uvicorn
    logging.info("Iniciando FastAPI (Google Ads) na porta 8080")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

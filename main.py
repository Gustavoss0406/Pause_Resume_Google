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
                raise HTTPException(502, f"Erro ao listar contas: {text}")
            names = json.loads(text).get("resourceNames", [])
            if not names:
                raise HTTPException(502, "Nenhuma conta acessível encontrada.")
            return names[0].split("/")[-1]

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
    logging.debug(f"[mutate] POST {url}")
    logging.debug(f"[mutate] body={json.dumps(body)}")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body) as resp:
            text = await resp.text()
            logging.debug(f"[mutate] status={resp.status}, body={text}")
            if resp.status != 200:
                raise HTTPException(resp.status, f"Erro ao mutar status: {text}")
            return await resp.json()

@app.post("/pause_google_campaign")
async def pause_google_campaign(payload: dict = Body(...)):
    """
    Pausa uma campanha definindo explicitamente status = 'PAUSED'.
    """
    logging.debug(f"[pause] Payload: {json.dumps(payload)}")
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "É necessário 'refresh_token' e 'campaign_id'.")

    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    # aqui garantimos que usamos exatamente "PAUSED"
    mutate_resp = await mutate_campaign_status(customer_id, campaign_id, "PAUSED", access_token)
    logging.info(f"[pause] Campaign {campaign_id} status set to PAUSED in customer {customer_id}")

    return {
        "success": True,
        "customer_id":  customer_id,
        "campaign_id":  campaign_id,
        "mutate_response": mutate_resp
    }

@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    """
    Reativa uma campanha definindo status = 'ENABLED'.
    """
    logging.debug(f"[resume] Payload: {json.dumps(payload)}")
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "É necessário 'refresh_token' e 'campaign_id'.")

    access_token = await get_access_token(refresh_token)
    customer_id  = payload.get("customer_id") or await discover_customer_id(access_token)

    mutate_resp = await mutate_campaign_status(customer_id, campaign_id, "ENABLED", access_token)
    logging.info(f"[resume] Campaign {campaign_id} status set to ENABLED in customer {customer_id}")

    return {
        "success": True,
        "customer_id":  customer_id,
        "campaign_id":  campaign_id,
        "mutate_response": mutate_resp
    }

if __name__ == "__main__":
    import uvicorn
    logging.info("Iniciando FastAPI (Google Ads pause/resume) na porta 8080")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

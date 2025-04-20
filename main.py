import logging
import json
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import aiohttp
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

# Credenciais Google Ads / OAuth2
DEVELOPER_TOKEN = "D4yv61IQ8R0JaE5dxrd1Uw"
CLIENT_ID       = "167266694231-g7hvta57r99etbp3sos3jfi7q7h4ef44.apps.googleusercontent.com"
CLIENT_SECRET   = "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"
REDIRECT_URI    = "https://app.adstock.ai/dashboard"

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
app = FastAPI()

# CORS configurado para seu frontend e o próprio domínio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.adstock.ai", "https://pauseresumegoogle-production.up.railway.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/pause_google_campaign")
async def pause_google_campaign(payload: dict = Body(...)):
    # 1) Log do payload
    try:
        logging.debug(f"[pause] Payload recebido: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    except:
        logging.debug(f"[pause] Payload recebido (raw): {payload}")

    # 2) Extrai campos
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        logging.error("[pause] refresh_token ou campaign_id ausentes")
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")

    # 3) Renova access token
    logging.debug("[pause] Renovando access token...")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    try:
        creds.refresh(GoogleRequest())
        access_token = creds.token
        logging.debug(f"[pause] Access token obtido: {access_token[:10]}…")
    except Exception as e:
        logging.exception("[pause] Falha ao renovar access token")
        raise HTTPException(status_code=502, detail=f"Erro ao obter access token: {e}")

    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }

    # 4) Determina customer_id
    customer_id = payload.get("customer_id")
    if not customer_id:
        logging.debug("[pause] customer_id não fornecido, consultando listAccessibleCustomers via POST...")
        url_list = "https://googleads.googleapis.com/v14/customers:listAccessibleCustomers"
        async with aiohttp.ClientSession() as session:
            async with session.post(url_list, headers=headers) as resp:
                logging.debug(f"[pause] listAccessibleCustomers status: {resp.status}")
                raw = await resp.text()
                logging.debug(f"[pause] listAccessibleCustomers raw response: {raw}")
                try:
                    body = json.loads(raw)
                except:
                    body = {}
                resource_names = body.get("resourceNames", [])
                if resp.status != 200 or not resource_names:
                    logging.error(f"[pause] Não foi possível obter resourceNames: {body}")
                    raise HTTPException(status_code=502, detail=f"Erro ao obter customer_id: {body}")
                customer_id = resource_names[0].split("/")[1]
                logging.debug(f"[pause] customer_id detectado: {customer_id}")
    else:
        logging.debug(f"[pause] Usando customer_id do payload: {customer_id}")

    # 5) PATCH para pausar
    url_pause = f"https://googleads.googleapis.com/v14/customers/{customer_id}/campaigns/{campaign_id}"
    params    = {"updateMask": "status"}
    json_body = {"status": "PAUSED"}
    logging.debug(f"[pause] Enviando PATCH para {url_pause} params={params} body={json_body}")
    async with aiohttp.ClientSession() as session:
        async with session.patch(url_pause, params=params, headers=headers, json=json_body) as resp:
            text = await resp.text()
            logging.debug(f"[pause] Resposta PATCH {resp.status}: {text}")
            if resp.status != 200:
                logging.error(f"[pause] Erro ao pausar campanha: {resp.status} {text}")
                raise HTTPException(status_code=resp.status, detail=text)

    logging.info(f"[pause] Campanha {campaign_id} pausada na conta {customer_id}")
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id}


@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    logging.debug(f"[resume] Payload recebido: {payload}")
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        logging.error("[resume] refresh_token ou campaign_id ausentes")
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")

    logging.debug("[resume] Renovando access token...")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    try:
        creds.refresh(GoogleRequest())
        access_token = creds.token
        logging.debug(f"[resume] Access token obtido: {access_token[:10]}…")
    except Exception as e:
        logging.exception("[resume] Falha ao renovar access token")
        raise HTTPException(status_code=502, detail=f"Erro ao obter access token: {e}")

    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }

    customer_id = payload.get("customer_id")
    if not customer_id:
        logging.debug("[resume] customer_id não fornecido, consultando listAccessibleCustomers via POST...")
        url_list = "https://googleads.googleapis.com/v14/customers:listAccessibleCustomers"
        async with aiohttp.ClientSession() as session:
            async with session.post(url_list, headers=headers) as resp:
                logging.debug(f"[resume] listAccessibleCustomers status: {resp.status}")
                raw = await resp.text()
                logging.debug(f"[resume] listAccessibleCustomers raw response: {raw}")
                try:
                    body = json.loads(raw)
                except:
                    body = {}
                resource_names = body.get("resourceNames", [])
                if resp.status != 200 or not resource_names:
                    logging.error(f"[resume] Não foi possível obter resourceNames: {body}")
                    raise HTTPException(status_code=502, detail=f"Erro ao obter customer_id: {body}")
                customer_id = resource_names[0].split("/")[1]
                logging.debug(f"[resume] customer_id detectado: {customer_id}")
    else:
        logging.debug(f"[resume] Usando customer_id do payload: {customer_id}")

    url_resume = f"https://googleads.googleapis.com/v14/customers/{customer_id}/campaigns/{campaign_id}"
    params     = {"updateMask": "status"}
    json_body  = {"status": "ACTIVE"}
    logging.debug(f"[resume] Enviando PATCH para {url_resume} params={params} body={json_body}")
    async with aiohttp.ClientSession() as session:
        async with session.patch(url_resume, params=params, headers=headers, json=json_body) as resp:
            text = await resp.text()
            logging.debug(f"[resume] Resposta PATCH {resp.status}: {text}")
            if resp.status != 200:
                logging.error(f"[resume] Erro ao reativar campanha: {resp.status} {text}")
                raise HTTPException(status_code=resp.status, detail=text)

    logging.info(f"[resume] Campanha {campaign_id} reativada na conta {customer_id}")
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id}


if __name__ == "__main__":
    import uvicorn
    logging.info("Iniciando FastAPI (Google Ads) na porta 8080")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

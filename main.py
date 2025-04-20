import logging
from fastapi import FastAPI, HTTPException, Body
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

@app.post("/pause_google_campaign")
async def pause_google_campaign(payload: dict = Body(...)):
    """
    Pausa uma campanha no Google Ads usando:
      - refresh_token
      - campaign_id
    Se não passar customer_id no payload, busca automaticamente o primeiro acessível.
    """
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")

    # 1) Renova o access token
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

    # 2) Se não veio customer_id, busca o primeiro acessível
    customer_id = payload.get("customer_id")
    if not customer_id:
        url_list = "https://googleads.googleapis.com/v14/customers:listAccessibleCustomers"
        async with aiohttp.ClientSession() as session:
            async with session.get(url_list, headers=headers) as resp:
                body = await resp.json()
                logging.debug(f"[pause] listAccessibleCustomers → {body}")
                if resp.status != 200 or not body.get("resourceNames"):
                    raise HTTPException(
                        status_code=502,
                        detail=f"Não foi possível obter customer_id: {body}"
                    )
                first = body["resourceNames"][0]  # ex: "customers/1234567890"
                customer_id = first.split("/")[1]
                logging.debug(f"[pause] customer_id detectado: {customer_id}")

    # 3) Faz PATCH pra pausar a campanha
    url_pause = f"https://googleads.googleapis.com/v14/customers/{customer_id}/campaigns/{campaign_id}"
    params    = {"updateMask": "status"}
    json_body = {"status": "PAUSED"}

    logging.debug(f"[pause] PATCH {url_pause} params={params} body={json_body}")
    async with aiohttp.ClientSession() as session:
        async with session.patch(url_pause, params=params, headers=headers, json=json_body) as resp:
            text = await resp.text()
            logging.debug(f"[pause] Resposta {resp.status}: {text}")
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail=text)

    logging.info(f"[pause] Campanha {campaign_id} pausada na conta {customer_id}")
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id}


@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    """
    Reativa uma campanha pausada no Google Ads.
      - refresh_token
      - campaign_id
    """
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(status_code=400, detail="É necessário 'refresh_token' e 'campaign_id'.")

    # Renova token
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

    # Descobre customer_id se não fornecido
    customer_id = payload.get("customer_id")
    if not customer_id:
        url_list = "https://googleads.googleapis.com/v14/customers:listAccessibleCustomers"
        async with aiohttp.ClientSession() as session:
            async with session.get(url_list, headers=headers) as resp:
                body = await resp.json()
                logging.debug(f"[resume] listAccessibleCustomers → {body}")
                if resp.status != 200 or not body.get("resourceNames"):
                    raise HTTPException(status_code=502, detail=f"Cannot get customer_id: {body}")
                customer_id = body["resourceNames"][0].split("/")[1]

    # Faz PATCH para reativar
    url_resume = f"https://googleads.googleapis.com/v14/customers/{customer_id}/campaigns/{campaign_id}"
    params     = {"updateMask": "status"}
    json_body  = {"status": "ACTIVE"}

    logging.debug(f"[resume] PATCH {url_resume} params={params} body={json_body}")
    async with aiohttp.ClientSession() as session:
        async with session.patch(url_resume, params=params, headers=headers, json=json_body) as resp:
            text = await resp.text()
            logging.debug(f"[resume] Resposta {resp.status}: {text}")
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail=text)

    logging.info(f"[resume] Campanha {campaign_id} reativada na conta {customer_id}")
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id}


if __name__ == "__main__":
    import uvicorn
    logging.info("Iniciando FastAPI (Google Ads) na porta 8080")
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

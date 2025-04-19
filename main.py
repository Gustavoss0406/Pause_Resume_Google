import os
import logging
from fastapi import FastAPI, HTTPException, Body
import aiohttp
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

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

    # Env vars obrigatórias
    client_id       = os.getenv("GOOGLE_CLIENT_ID")
    client_secret   = os.getenv("GOOGLE_CLIENT_SECRET")
    developer_token = os.getenv("GOOGLE_DEVELOPER_TOKEN")
    if not client_id or not client_secret or not developer_token:
        raise HTTPException(status_code=500, detail="Configuração do Google Ads faltando no servidor.")

    # 1) Renova o access token
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    try:
        creds.refresh(GoogleRequest())
        access_token = creds.token
        logging.debug(f"[pause] Access token: {access_token[:10]}…")
    except Exception as e:
        logging.exception("[pause] Falha ao renovar access token")
        raise HTTPException(status_code=502, detail=f"Erro ao obter access token: {e}")

    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": developer_token,
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
                # resourceNames = ["customers/1234567890", ...]
                first = body["resourceNames"][0]
                customer_id = first.split("/")[1]
                logging.debug(f"[pause] customer_id detectado: {customer_id}")

    # 3) Faz PATCH pra pausar a campanha
    url_pause = f"https://googleads.googleapis.com/v14/customers/{customer_id}/campaigns/{campaign_id}"
    params  = {"updateMask": "status"}
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8090, reload=True)

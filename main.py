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

# CORS – ajuste conforme seu front
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

async def list_accessible_customers(access_token: str) -> list[str]:
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers:listAccessibleCustomers"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    logging.debug(f"[list_customers] GET {url} headers={headers}")
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            logging.debug(f"[list_customers] status={resp.status}, body={text}")
            if resp.status != 200:
                raise HTTPException(status_code=502, detail=f"Erro listAccessibleCustomers: {text}")
            names = json.loads(text).get("resourceNames", [])
            return [n.split("/")[-1] for n in names]

async def find_customer_for_campaign(access_token: str, campaign_id: str) -> str:
    customers = await list_accessible_customers(access_token)
    query = f"SELECT campaign.resource_name FROM campaign WHERE campaign.id = {campaign_id} LIMIT 1"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    for cid in customers:
        url = f"https://googleads.googleapis.com/{API_VERSION}/customers/{cid}/googleAds:search"
        body = {"query": query}
        logging.debug(f"[find_customer] POST {url} headers={headers} body={body}")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as resp:
                text = await resp.text()
                logging.debug(f"[find_customer] customer={cid} status={resp.status}, body={text}")
                if resp.status == 200:
                    data = json.loads(text)
                    if data.get("results"):
                        logging.info(f"[find_customer] Campaign {campaign_id} found in customer {cid}")
                        return cid
    raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

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
    logging.debug(f"[mutate] headers: {headers}")
    logging.debug(f"[mutate] body: {json.dumps(body)}")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body) as resp:
            text = await resp.text()
            logging.debug(f"[mutate] response status={resp.status}, body={text}")
            if resp.status != 200:
                # relança com detalhe completo
                raise HTTPException(status_code=resp.status, detail=text)
            return json.loads(text)

@app.post("/pause_google_campaign")
async def pause_google_campaign(payload: dict = Body(...)):
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "Need 'refresh_token' and 'campaign_id'")
    access_token = await get_access_token(refresh_token)
    customer_id  = await find_customer_for_campaign(access_token, campaign_id)
    result = await mutate_campaign_status(customer_id, campaign_id, "PAUSED", access_token)
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id, "response": result}

@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "Need 'refresh_token' and 'campaign_id'")
    access_token = await get_access_token(refresh_token)
    customer_id  = await find_customer_for_campaign(access_token, campaign_id)
    result = await mutate_campaign_status(customer_id, campaign_id, "ENABLED", access_token)
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id, "response": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
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

# CORS – ajuste conforme seu front
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

async def list_accessible_customers(access_token: str) -> list[str]:
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers:listAccessibleCustomers"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    logging.debug(f"[list_customers] GET {url} headers={headers}")
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            logging.debug(f"[list_customers] status={resp.status}, body={text}")
            if resp.status != 200:
                raise HTTPException(status_code=502, detail=f"Erro listAccessibleCustomers: {text}")
            names = json.loads(text).get("resourceNames", [])
            return [n.split("/")[-1] for n in names]

async def find_customer_for_campaign(access_token: str, campaign_id: str) -> str:
    customers = await list_accessible_customers(access_token)
    query = f"SELECT campaign.resource_name FROM campaign WHERE campaign.id = {campaign_id} LIMIT 1"
    headers = {
        "Authorization":   f"Bearer {access_token}",
        "developer-token": DEVELOPER_TOKEN,
        "Content-Type":    "application/json"
    }
    for cid in customers:
        url = f"https://googleads.googleapis.com/{API_VERSION}/customers/{cid}/googleAds:search"
        body = {"query": query}
        logging.debug(f"[find_customer] POST {url} headers={headers} body={body}")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as resp:
                text = await resp.text()
                logging.debug(f"[find_customer] customer={cid} status={resp.status}, body={text}")
                if resp.status == 200:
                    data = json.loads(text)
                    if data.get("results"):
                        logging.info(f"[find_customer] Campaign {campaign_id} found in customer {cid}")
                        return cid
    raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

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
    logging.debug(f"[mutate] headers: {headers}")
    logging.debug(f"[mutate] body: {json.dumps(body)}")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body) as resp:
            text = await resp.text()
            logging.debug(f"[mutate] response status={resp.status}, body={text}")
            if resp.status != 200:
                # relança com detalhe completo
                raise HTTPException(status_code=resp.status, detail=text)
            return json.loads(text)

@app.post("/pause_google_campaign")
async def pause_google_campaign(payload: dict = Body(...)):
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "Need 'refresh_token' and 'campaign_id'")
    access_token = await get_access_token(refresh_token)
    customer_id  = await find_customer_for_campaign(access_token, campaign_id)
    result = await mutate_campaign_status(customer_id, campaign_id, "PAUSED", access_token)
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id, "response": result}

@app.post("/resume_google_campaign")
async def resume_google_campaign(payload: dict = Body(...)):
    refresh_token = payload.get("refresh_token")
    campaign_id   = payload.get("campaign_id")
    if not refresh_token or not campaign_id:
        raise HTTPException(400, "Need 'refresh_token' and 'campaign_id'")
    access_token = await get_access_token(refresh_token)
    customer_id  = await find_customer_for_campaign(access_token, campaign_id)
    result = await mutate_campaign_status(customer_id, campaign_id, "ENABLED", access_token)
    return {"success": True, "customer_id": customer_id, "campaign_id": campaign_id, "response": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

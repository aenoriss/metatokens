from fastapi import FastAPI
from firebase_admin import credentials
from firebase_admin import firestore
import httpx
import asyncio
import os
from dotenv import load_dotenv


app = FastAPI()
load_dotenv()

cred = credentials.Certificate(os.getenv('FIREBASE_CREDENTIALS_PATH'))
http_client = httpx.AsyncClient()

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get("/getTokens")
async def get_tokens():
    response = await http_client.get("https://api.dexscreener.com/token-profiles/latest/v1")
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": f"Failed to fetch data: {response.status_code}"}
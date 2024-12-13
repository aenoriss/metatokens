from fastapi import FastAPI
import uvicorn
import firebase_admin
from firebase_admin import credentials, storage
import httpx
from contextlib import asynccontextmanager
from PIL import Image
import os
import io
from dotenv import load_dotenv
from urllib.parse import urlparse
from datetime import datetime
from firebase_admin import db
import asyncio
import time
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.cloud import secretmanager
import os

app = FastAPI()
http_client = httpx.AsyncClient()
load_dotenv()
auth_scheme = HTTPBearer()

cred = credentials.Certificate(os.getenv('FIREBASE_CREDENTIALS_PATH'))

firebase_admin.initialize_app(cred, {
    "apiKey": "AIzaSyAniJ6mDrIlcBpgKZ1YGukVfsQTHkst6BU",
    "authDomain": "xrb-prototype1-backend.firebaseapp.com",
    "databaseURL": "https://xrb-prototype1-backend-default-rtdb.firebaseio.com",
    "projectId": "xrb-prototype1-backend",
    "storageBucket": "xrb-prototype1-backend.firebasestorage.app",
    "messagingSenderId": "534370711592",
    "appId": "1:534370711592:web:a76ba4da337d343ec29d1d"
})

def get_secret():
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/xrb-proto-1/secrets/API_KEY/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

API_KEY = get_secret()

async def verify_api_key(auth: HTTPAuthorizationCredentials = Security(auth_scheme)):
    if auth.credentials != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid token"
        )
    return auth.credentials

@asynccontextmanager
async def lifespan(app: FastAPI):
    
    global http_client
    http_client = httpx.AsyncClient()
    
    yield
    
    if http_client:
        await http_client.aclose()


@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get("/updateTokensIndex")
async def get_tokens():
    tokens_ref = db.reference('/tokens')
     
    existing_tokens = tokens_ref.get() or {}
    existing_addresses = set(token.get('tokenAddress') for token in existing_tokens.values() if token.get('tokenAddress'))
    
    response = await http_client.get("https://api.dexscreener.com/token-profiles/latest/v1")

    if response.status_code == 200:

        new_tokens = {}

        for token in response.json():
            token_address = token.get('tokenAddress')

            #get only new tokens on solana
            if token_address and token["chainId"] == "solana" and token_address not in existing_addresses:

                #Complete token data with pair info
                pair_data_request = await http_client.get("https://api.dexscreener.com/latest/dex/tokens/" + token_address)
                if pair_data_request.status_code == 200:
                    pair_data = pair_data_request.json()
                    token["name"] = pair_data["pairs"][0]["baseToken"]["name"]
                    token["symbol"] = pair_data["pairs"][0]["baseToken"]["symbol"]
                    token["dexId"] = pair_data["pairs"][0]["pairCreatedAt"]
                    token["price"] = pair_data["pairs"][0]["priceUsd"]
                    token["priceChange"] = pair_data["pairs"][0]["priceChange"]
                    token["creationDate"] = pair_data["pairs"][0]["pairCreatedAt"]
                else:
                    print(f"Failed to fetch pair data for {token_address}")

                #Convert logo webp image to PNG and save it in storage
                logo_url = await download_and_convert_image(token.get("icon"), token.get("tokenAddress"))

                if(logo_url):
                    token["icon"] = logo_url

                new_tokens[token_address] = token

        if new_tokens:
            print(f"Adding {len(new_tokens)} new tokens")
            tokens_ref.update(new_tokens)
                
    else:
        return {"error": f"Failed to fetch data: {response.status_code}"}


@app.get("/getTokensIndex")
async def get_tokens():
    tokens_ref = db.reference('/tokens')
    tokens = tokens_ref.get() or {}
    return tokens

@app.put("/cleanTokensIndex")
async def clean_tokens_index(auth: HTTPAuthorizationCredentials = Security(auth_scheme)):
    tokens_ref = db.reference('/tokens')
    tokens = tokens_ref.order_by_child('creationDate').get()

    current_time = time.time() * 1000 
    one_day_ago = current_time - (24 * 60 * 60 * 1000)

    sorted_tokens = sorted(tokens.items(), key=lambda x: x[1]['creationDate'], reverse=True)

    for address, data in sorted_tokens:
        should_delete = False
        
        # Check if older than 24h
        if data['creationDate'] < one_day_ago:
            should_delete = True
        
        # Check if beyond the 300 limit
        if sorted_tokens.index((address, data)) >= 300:
            should_delete = True
            
        if should_delete:
            tokens_ref.child(address).delete()

async def download_and_convert_image(url: str, tokenAddress: str):
    try:
        await asyncio.sleep(0.1)

        response = await http_client.get(url)

        if response.status_code != 200:
            return None
    
        #convert webp to png
        image = Image.open(io.BytesIO(response.content))
        
        # Create a temporary buffer to store the PNG
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        # Get bucket
        bucket = storage.bucket()

        # Create blob path using token name
        blob_path = f"token_icons/{tokenAddress}.png"
        blob = bucket.blob(blob_path)

        blob.upload_from_string(
            img_buffer.getvalue(),
            content_type='image/png'
        )

        blob.make_public()

        return blob.public_url


    
    except Exception as e:
        print(f"Error processing image {url}: {str(e)}")
        return None

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    )
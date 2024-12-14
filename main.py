from fastapi import FastAPI
import uvicorn
import firebase_admin
from firebase_admin import credentials, storage
import httpx
from contextlib import asynccontextmanager
from PIL import Image
import os
import io
from urllib.parse import urlparse
from datetime import datetime
from firebase_admin import db
import asyncio
import time
import os

app = FastAPI()
cred = credentials.Certificate("./firebase_key.json")

firebase_admin.initialize_app(cred, {
    "apiKey": "AIzaSyAniJ6mDrIlcBpgKZ1YGukVfsQTHkst6BU",
    "authDomain": "xrb-prototype1-backend.firebaseapp.com",
    "databaseURL": "https://xrb-prototype1-backend-default-rtdb.firebaseio.com",
    "projectId": "xrb-prototype1-backend",
    "storageBucket": "xrb-prototype1-backend.firebasestorage.app",
    "messagingSenderId": "534370711592",
    "appId": "1:534370711592:web:a76ba4da337d343ec29d1d"
})

http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0),
    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
    headers={
        "User-Agent": "YourAppName/1.0",
    }
)

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get("/updateTokensIndex")
async def updateTokensIndex():
    await clean_tokens_index()

    tokens_ref = db.reference('/tokens')
     
    existing_tokens = tokens_ref.get() or {}
    current_token_count = len(existing_tokens)
    
    slots_available = 250 - current_token_count
    
    if slots_available <= 0:
        return {"message": "Token limit reached (250), no new tokens added"}
        
    existing_addresses = set(token.get('tokenAddress') for token in existing_tokens.values() if token.get('tokenAddress'))
    
    response = await http_client.get("https://api.dexscreener.com/token-profiles/latest/v1")

    if response.status_code == 200:
        new_tokens = {}
        tokens_added = 0

        for token in response.json():
            if tokens_added >= slots_available:
                break
                
            token_address = token.get('tokenAddress')

            if token_address and token["chainId"] == "solana" and token_address not in existing_addresses:
                pair_data_request = await http_client.get("https://api.dexscreener.com/latest/dex/tokens/" + token_address)
                if pair_data_request.status_code == 200:
                    pair_data = pair_data_request.json()
                    token["name"] = pair_data["pairs"][0]["baseToken"]["name"]
                    token["symbol"] = pair_data["pairs"][0]["baseToken"]["symbol"]
                    token["dexId"] = pair_data["pairs"][0]["pairCreatedAt"]
                    token["price"] = pair_data["pairs"][0]["priceUsd"]
                    token["priceChange"] = pair_data["pairs"][0]["priceChange"]
                    token["creationDate"] = pair_data["pairs"][0]["pairCreatedAt"]
                    
                    logo_url = await download_and_convert_image(token.get("icon"), token.get("tokenAddress"))
                    if logo_url:
                        token["icon"] = logo_url

                    new_tokens[token_address] = token
                    tokens_added += 1
                else:
                    print(f"Failed to fetch pair data for {token_address}")

        if new_tokens:
            print(f"Adding {len(new_tokens)} new tokens")
            tokens_ref.update(new_tokens)
            return {
                "message": f"Added {len(new_tokens)} new tokens",
                "current_total": current_token_count + len(new_tokens)
            }
        else:
            return {"message": "No new tokens to add"}
                
    else:
        return {"error": f"Failed to fetch data: {response.status_code}"}


@app.get("/getTokensIndex")
async def get_tokens():
    tokens_ref = db.reference('/tokens')
    tokens = tokens_ref.get() or {}
    return tokens

async def clean_tokens_index():
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

    return {"message": "Tokens index cleaned"}

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
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(
        "main:app",  
        host="0.0.0.0",  
        port=port,
        reload=False  
    )


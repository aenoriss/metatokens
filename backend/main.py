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
http_client = httpx.AsyncClient()

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
                    token["volume"] = pair_data["pairs"][0]["volume"]["h6"]
                    token["txns"] = pair_data["pairs"][0]["txns"]["h6"]
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
            await updateTokensFinancials()
            return {
                "message": f"Added {len(new_tokens)} new tokens",
                "current_total": current_token_count + len(new_tokens)
            }
        else:
            return {"message": "No new tokens to add"}
                
    else:
        return {"error": f"Failed to fetch data: {response.status_code}"}
   

async def updateTokensFinancials():
    tokens_ref = db.reference('/tokens')
    existing_tokens = tokens_ref.get() or {}   
    new_tokens = {}
    tokens_added = 0

    for token_address, token_data in existing_tokens.items():
        try:
            pair_data_request = await http_client.get("https://api.dexscreener.com/latest/dex/tokens/" + token_address)
            
            if pair_data_request.status_code == 200:
                pair_data = pair_data_request.json()
                
                token_data["price"] = pair_data["pairs"][0]["priceUsd"]
                token_data["volume"] = pair_data["pairs"][0]["volume"]["h6"]
                token_data["txns"] = pair_data["pairs"][0]["txns"]["h6"]
                token_data["priceChange"] = pair_data["pairs"][0]["priceChange"]

                new_tokens[token_address] = token_data
                tokens_added += 1
            else:
                print(f"Failed to fetch pair data for {token_address}")

        except Exception as e:
            print(f"Error updating {token_address}: {str(e)}")
            continue

    if new_tokens:
        print(f"Updating {len(new_tokens)} tokens")
        tokens_ref.update(new_tokens)
        return {
            "message": f"Updated {len(new_tokens)} tokens",
            "current_total": len(new_tokens)
        }
    
    return {"message": "No tokens updated"}


@app.get("/getTokensIndex")
async def get_tokens():
    tokens_ref = db.reference('/tokens')
    tokens = tokens_ref.get() or {}
    return tokens

async def clean_tokens_index():
    try:
        tokens_ref = db.reference('/tokens')
        tokens = tokens_ref.order_by_child('creationDate').get()

        if not tokens:
            print("No tokens found in database")
            return {"message": "No tokens to clean"}

        current_time = time.time() * 1000 
        one_day_ago = current_time - (24 * 60 * 60 * 1000)

        sorted_tokens = sorted(tokens.items(), key=lambda x: x[1].get('creationDate', 0), reverse=True)

        deleted_count = 0
        for address, data in sorted_tokens:
            should_delete = False
            
            if data.get('creationDate', 0) < one_day_ago:
                should_delete = True
            
            if sorted_tokens.index((address, data)) >= 250:
                should_delete = True
                
            if should_delete:
                await eliminateImage(address)
                tokens_ref.child(address).delete()
                deleted_count += 1

        return {
            "message": f"Tokens index cleaned. Deleted {deleted_count} tokens",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        print(f"Error cleaning tokens index: {str(e)}")
        return {"error": f"Failed to clean tokens: {str(e)}"}

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
    
async def eliminateImage(tokenAddress: str):
    try:
        bucket = storage.bucket()
        
        blob_path = f"token_icons/{tokenAddress}.png"
        
        blob = bucket.blob(blob_path)
        
        if blob.exists():
            blob.delete()
            print(f"Successfully deleted image for token {tokenAddress}")
            return True
        else:
            print(f"No image found for token {tokenAddress}")
            return False
            
    except Exception as e:
        print(f"Error deleting image for token {tokenAddress}: {str(e)}")
        return False


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    )
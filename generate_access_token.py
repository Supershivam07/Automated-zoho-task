from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import requests
import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
import requests
import time

load_dotenv()

app = FastAPI()

# Load env variables
CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
PORTAL_ID = os.getenv("ZOHO_PORTAL_ID")
PROJECT_ID = os.getenv("ZOHO_PROJECT_ID")
TASKLIST_ID = os.getenv("ZOHO_TASKLIST_ID")
CODE = os.getenv("ZOHO_code")

def generate_tokens():
    url = "https://accounts.zoho.in/oauth/v2/token"

    payload = {
        "code": CODE,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": "http://localhost:8000/callback",
        "grant_type": "authorization_code"
    }

    response = requests.post(url, data=payload)

    print("STATUS:", response.status_code)
    print("RAW RESPONSE:", response.text)

    return response.json()

response = generate_tokens()
print("Generated Tokens:", response)

'''

how to get 

https://accounts.zoho.com/oauth/v2/auth?
scope=ZohoProjects.tasks.ALL&
client_id=1000.CAQVQRZGZPDHCTF4XXD88X0LYT3PYV&
response_type=code&
access_type=offline&
redirect_uri=http://localhost:8000/callback

'''
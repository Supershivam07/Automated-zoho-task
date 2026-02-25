from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import requests
import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
import requests
import time
import requests
from fastapi import HTTPException

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
REDIRECT_URI = os.getenv("ZOHO_REDIRECT_URI")
access_token = os.getenv("ZOHO_ACCESS_TOKEN")
ZOHO_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"

def get_access_token():
    url = "https://accounts.zoho.in/oauth/v2/token"

    payload = {
        "code": CODE,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    response = requests.post(url, data=payload)

    print(response.status_code, 'status code')
    print(response.text, 'status text')

    if response.status_code != 200:
        print("Zoho Token Error:", response.text)
        raise HTTPException(status_code=401, detail="Failed to get Zoho access token")

    try:
        token_data = response.json()
    except Exception:
        print("Invalid JSON response:", response.text)
        raise HTTPException(status_code=500, detail="Zoho returned invalid response")

    if "access_token" not in token_data:
        print("Token response:", token_data)
        raise HTTPException(status_code=401, detail="Access token not found")

    print("Access token obtained:---------------------------------------------------", token_data["access_token"])
    # print("Refresh token obtained:---------------------------------------------------", token_data.get("refresh_token"))
    print("Scope:---------------------------------------------------", token_data.get("scope"))
    
    return token_data


run_fucntion = get_access_token()
print(run_fucntion)


# def refresh_access_token():
#     """Refresh Zoho access token using the refresh token from env.

#     Persists the new access token back to the .env file and returns it.
#     Raises HTTPException if refresh fails or REFRESH_TOKEN is not configured.
#     """
#     if not REFRESH_TOKEN or not CLIENT_ID or not CLIENT_SECRET:
#         raise HTTPException(status_code=401, detail="Missing refresh token or client credentials. Please generate a new token manually.")

#     url = "https://accounts.zoho.in/oauth/v2/token"
#     payload = {
#         "refresh_token": REFRESH_TOKEN,
#         "client_id": CLIENT_ID,
#         "client_secret": CLIENT_SECRET,
#         "grant_type": "refresh_token"
#     }

#     resp = requests.post(url, data=payload)
#     try:
#         data = resp.json()
#     except Exception:
#         raise HTTPException(status_code=500, detail="Invalid response from Zoho token endpoint")

#     if resp.status_code != 200 or "access_token" not in data:
#         # token refresh failed — instruct user to generate a new token
#         raise HTTPException(status_code=401, detail=f"Failed to refresh access token: {data}")

#     new_token = data["access_token"]
#     # update runtime and persist to .env
#     os.environ["ZOHO_ACCESS_TOKEN"] = new_token
#     _write_env_var("ZOHO_ACCESS_TOKEN", new_token)

#     return new_token


# @app.post("/tasks")
# def create_task():
#     token = get_valid_access_token()
    
#     headers = {
#         "Authorization": f"Zoho-oauthtoken {token}",
#         "Content-Type": "application/json"
#     }
#     scope = [
#         "https://www.googleapis.com/auth/spreadsheets",
#         "https://www.googleapis.com/auth/drive"
#     ]
#     creds = Credentials.from_service_account_file(
#         "credentials.json",
#         scopes=scope
#     )
#     client = gspread.authorize(creds)
#     spreadsheet = client.open_by_key(
#         "1IHBNbK5siAwRIkVKKeLPnd6r4zzNMMwyPZ3cu6THdJM"
#     )
#     all_sheets = spreadsheet.worksheets()

#     # Fetch all projects ONCE from the API
#     print("Fetching all projects from Zoho API...")
#     all_projects = get_all_projects()
#     print(f"API call complete. Cached {len(all_projects)} projects in memory.")

#     created_tasks = []
#     for sheet in all_sheets:
#         for sheet_data in sheet.get_all_records():
#             value = sheet_data['Project code']
#             sheet_data['Project code'] = value.replace("CS-", "")

#             # Get the project ID by matching the key from cached data (NO API CALL)
#             project_key = sheet_data['Project code']
#             project_id = get_project_id_from_cache(project_key, all_projects)
            
#             if not project_id:
#                 print(f"Warning: No project found with key '{project_key}'. Skipping this row.")
#                 continue
            
#             print(f"Found project ID: {project_id} for key: {project_key}")

#             task_payload = {
#                 "name": sheet_data["Title"],
#                 "description": sheet_data.get("Description", ""),
#             }
            
#             # Add duration if available
#             duration_raw = sheet_data.get("Duration", "")
#             duration_obj = parse_duration_to_duration_object(duration_raw)

#             print(duration_obj, 'parsed duration object')

#             if duration_obj:
#                 task_payload["duration"] = duration_obj
#                 print(f"Duration added: {duration_obj}")
            
#             # Add task owner if available
#             task_owner = sheet_data.get("Task Owner", "")
#             if task_owner and str(task_owner).strip() != "":
#                 task_payload["task_owner"] = task_owner

#             # Debug: show final payload being sent
#             print("Final task payload:", json.dumps(task_payload))

#             PROJECT_ID = project_id  # Use the dynamically found project ID
#             parent_task_id = sheet_data.get("Parent_id")
#             if parent_task_id and str(parent_task_id).strip() != "":
#                 parent_id = str(parent_task_id).strip()
#                 if not re.match(r"^[0-9]+$", parent_id):
#                     raise HTTPException(status_code=400, detail=f"Invalid Parent_id '{parent_id}'. Provide numeric Zoho task id.")

#                 url = f"https://projectsapi.zoho.in/api/v3/portal/{PORTAL_ID}/projects/{PROJECT_ID}/tasks"
#                 print(url, 'task creation url')
#                 task_payload["parental_info"] = {"parent_task_id": parent_id}
#                 response = requests.post(url, headers=headers, json=task_payload)
#             else:
#                 url = f"https://projectsapi.zoho.in/api/v3/portal/{PORTAL_ID}/projects/{PROJECT_ID}/tasks"
#                 print(url, 'task creation url')
#                 response = requests.post(url, headers=headers, json=task_payload)

#             if response.status_code in (401, 403):
#                 token = get_access_token()
#                 headers["Authorization"] = f"Zoho-oauthtoken {token}"
#                 response = requests.post(url, headers=headers, json=task_payload)

#             print(f"Status Code: {response.status_code}")
#             print(f"Response: {response.text}")

#             if response.status_code not in (200, 201):
#                 print(f"Zoho Error: {response.text}")
#                 raise HTTPException(
#                     status_code=response.status_code,
#                     detail=response.text
#                 )

#             created_tasks.append(response.json())

#     return {
#         "message": "Tasks created successfully",
#         "tasks": created_tasks
#     }


# def get_portal_users():
#     """Fetch all users from the Zoho portal and return a mapping of name/id to zpuid."""
#     token = get_valid_access_token()
#     url = f"https://projectsapi.zoho.in/api/v3/portal/{PORTAL_ID}/users"
#     headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    
#     response = requests.get(url, headers=headers)
#     if response.status_code != 200:
#         print(f"Error fetching users: {response.text}")
#         return {}
        
#     users_data = response.json().get("users", [])
#     user_map = {}
#     for user in users_data:
#         zpuid = str(user.get("zpuid"))
#         name = str(user.get("name")).strip().lower()
#         email = str(user.get("email")).strip().lower()
        
#         # Map by ID, Name, and Email for flexibility
#         user_map[zpuid] = zpuid
#         user_map[name] = zpuid
#         user_map[email] = zpuid
        
#     return user_map
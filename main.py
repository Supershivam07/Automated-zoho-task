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
from pathlib import Path
import json
import re
from fastapi import FastAPI, HTTPException, Query

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

    # Using authorization code flow with x-www-form-urlencoded
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
    # persist access token to runtime and .env so other calls can reuse
    new_token = token_data["access_token"]
    os.environ["ZOHO_ACCESS_TOKEN"] = new_token
    try:
        _write_env_var("ZOHO_ACCESS_TOKEN", new_token)
    except Exception:
        # non-fatal: if writing to .env fails, continue with runtime token
        print("Warning: failed to persist ZOHO_ACCESS_TOKEN to .env")

    return new_token


def _write_env_var(key: str, value: str, env_path: str = ".env"):
    """Write or update a key=value pair in a .env file in workspace root."""
    p = Path(env_path)
    lines = []
    if p.exists():
        lines = p.read_text(encoding="utf-8").splitlines()

    key_eq = f"{key}="
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(key_eq):
            lines[i] = f"{key}={value}"
            updated = True
            break

    if not updated:
        lines.append(f"{key}={value}")

    p.write_text("\n".join(lines), encoding="utf-8")

def get_valid_access_token():
    """Return a valid access token. If missing or invalid, attempt refresh using the refresh token.

    Raises HTTPException with a clear message when refresh is not possible.
    """
    token = os.getenv("ZOHO_ACCESS_TOKEN")
    if token and str(token).strip() != "":
        return token

    return get_access_token()


def get_all_projects():
    """Fetch all projects from Zoho API once and return as a list.
    
    Handles pagination and returns all projects across all pages.
    Returns:
        List of all projects
    """
    token = get_valid_access_token()
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}"
    }
    url = f"https://projectsapi.zoho.in/api/v3/portal/{PORTAL_ID}/projects"
    
    all_projects = []
    page = 1
    per_page = 200
    
    while True:
        params = {
            "page": page,
            "per_page": per_page
        }
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code in (401, 403):
            token = get_access_token()
            headers["Authorization"] = f"Zoho-oauthtoken {token}"
            response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        
        data = response.json()
        print(f"Fetched page {page} of projects", 'project list response')

        # Handle both list and dict responses
        if isinstance(data, list):
            projects = data
        else:
            projects = data.get("projects", [])
        
        all_projects.extend(projects)
        
        if len(projects) < per_page:
            break  # No more pages
        page += 1
    
    print(f"Total projects fetched: {len(all_projects)}")
    return all_projects


def get_project_id_from_cache(key: str, projects_cache: list):
    """Find project ID from cached projects list by matching key.
    
    Args:
        key: The project key to search for (e.g., "255")
        projects_cache: List of all projects to search in
        
    Returns:
        The project ID if found, None otherwise
    """
    for project in projects_cache:
        if str(project.get("key")) == str(key):
            return project.get("id")
    return None


def _parse_duration_to_hours(duration_raw: str):
    """Parse common duration formats to a numeric hours value.

    Accepts values like: '8', '8h', '8 h', '1.5', '90m', '2d'. Returns float hours or None.
    """
    if duration_raw is None:
        return None

    s = str(duration_raw).strip().lower()
    if s == "":
        return None

    # pure number -> hours
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)", s)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None

    # days
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(d|day|days)", s)
    if m:
        return float(m.group(1)) * 24

    # hours
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(h|hr|hrs|hour|hours)", s)
    if m:
        return float(m.group(1))

    # minutes
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(m|min|mins|minute|minutes)", s)
    if m:
        return float(m.group(1)) / 60.0

    # fallback: extract first number
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", s)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None

    return None


def parse_duration_to_duration_object(duration_raw: str):
    """Parse duration string and return duration object for Zoho API v3.
    
    Accepts: '90', '90d', '90 days', '8h', '8 hours', '120m', '120 minutes'
    Returns: {"value": "HH:MM", "type": "hours"} (formatted as string per API requirements)
    
    Args:
        duration_raw: Duration string from sheet
        
    Returns:
        Dict with "value" and "type" keys, or None if invalid
    """
    if duration_raw is None or str(duration_raw).strip() == "":
        return None
    
    s = str(duration_raw).strip().lower()
    
    # helper to format float hours to HH:MM string
    def format_to_hh_mm(hours_float):
        h = int(hours_float)
        m = int(round((hours_float - h) * 60))
        return f"{h:02d}:{m:02d}"

    # days - convert to hours (1 day = 8 hours)
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(d|day|days)?", s)
    if m:
        value_days = float(m.group(1))
        value_hours = value_days * 8
        return {"value": format_to_hh_mm(value_hours), "type": "hours"}
    
    # hours
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(h|hr|hrs|hour|hours)", s)
    if m:
        value_hours = float(m.group(1))
        return {"value": format_to_hh_mm(value_hours), "type": "hours"}
    
    # minutes - convert to hours
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(m|min|mins|minute|minutes)", s)
    if m:
        value_minutes = float(m.group(1))
        value_hours = value_minutes / 60
        return {"value": format_to_hh_mm(value_hours), "type": "hours"}
    
    return None

def get_portal_users():
    """Fetch all users from users_raw.json and return a mapping of name/id to user id."""
    RAW_FILE = "users_raw.json"
    
    if not os.path.exists(RAW_FILE):
        print(f"Error: {RAW_FILE} not found. Please create it with user data.")
        return {}
        
    try:
        with open(RAW_FILE, "r") as f:
            raw_data = json.load(f)
            
        # Extract users from standard /users response
        users_data = []
        if isinstance(raw_data, dict):
            if "users" in raw_data:
                users_data = raw_data["users"]
            elif "tasks" in raw_data: # Fallback if data is from a legacy source
                for t in raw_data["tasks"]:
                    if "owners_and_work" in t:
                        users_data.extend(t["owners_and_work"].get("owners", []))
                    if "created_by" in t:
                        users_data.append(t["created_by"])
        
        user_map = {}
        for user in users_data:
            # Use the "zuid" field from users_raw.json as the ZPUID
            user_zuid = str(user.get("id", "")).strip()
            
            if user_zuid and user_zuid != "0": # Skip unassigned/empty
                # Map various identifiers to the zuid
                user_id_raw = str(user.get("id", "")).strip()
                user_map[user_id_raw] = user_zuid
                
                full_name = str(user.get("full_name", "")).strip().lower()
                first_name = str(user.get("first_name", "")).strip().lower()
                display_name = str(user.get("display_name", "")).strip().lower()
                email = str(user.get("email", "")).strip().lower()
                
                if full_name and "unassigned" not in full_name:
                    user_map[full_name] = user_zuid
                if first_name and "unassigned" not in first_name:
                    user_map[first_name] = user_zuid
                if display_name and "unassigned" not in display_name:
                    user_map[display_name] = user_zuid
                if email and "unassigned" not in email:
                    user_map[email] = user_zuid
                    
        print(f"Loaded {len(user_map)} user identifiers mapping to ZUIDs from {RAW_FILE}.")
        return user_map
        
    except Exception as e:
        print(f"Error parsing {RAW_FILE}: {e}")
        return {}


@app.post("/tasks")
def create_task():
    token = get_valid_access_token()
    
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json"
    }
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(
        "credentials.json",
        scopes=scope
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(
        "1IHBNbK5siAwRIkVKKeLPnd6r4zzNMMwyPZ3cu6THdJM"
    )
    all_sheets = spreadsheet.worksheets()

    # Fetch all projects and users ONCE from the API
    all_projects = get_all_projects()
    user_map = get_portal_users()

    created_tasks = []
    for sheet in all_sheets:
        for sheet_data in sheet.get_all_records():
            # Get project ID
            project_code_raw = str(sheet_data.get('Project code', ''))
            project_key = project_code_raw.replace("CS-", "").strip()
            project_id = get_project_id_from_cache(project_key, all_projects)
            
            if not project_id:
                print(f"Warning: No project found with key '{project_key}'. Skipping row.")
                continue
            
            # Build Task Payload
            task_payload = {
                "name": str(sheet_data.get("Title", "Untitled Task")),
                "description": str(sheet_data.get("Description", "")),
            }

            # 2. Add Duration (Planned Duration)
            duration_raw = sheet_data.get("Duration", "")
            duration_obj = parse_duration_to_duration_object(duration_raw)
            if duration_obj:
                task_payload["duration"] = duration_obj

            # Support Name, ID, or Email from "Task Owner" column
            owner_input = str(sheet_data.get("Task Owner", "")).strip().lower()
            if owner_input:
                zpuid = user_map.get(owner_input)
                if zpuid:
                    # In v3, some setups require this specific owners_and_work structure

                    task_payload["owners_and_work"] = {
                        "owners": [
                            {
                                "add": [
                                    {
                                        "zpuid": zpuid
                                    }
                                ]
                            }
                        ]
                    }

            # Debug: show final payload being sent
            print("Final task payload:", json.dumps(task_payload))

            PROJECT_ID = project_id  # Use the dynamically found project ID
            parent_task_id = sheet_data.get("Parent_id")
            if parent_task_id and str(parent_task_id).strip() != "":
                parent_id = str(parent_task_id).strip()
                if not re.match(r"^[0-9]+$", parent_id):
                    raise HTTPException(status_code=400, detail=f"Invalid Parent_id '{parent_id}'. Provide numeric Zoho task id.")

                url = f"https://projectsapi.zoho.in/api/v3/portal/{PORTAL_ID}/projects/{PROJECT_ID}/tasks"
                task_payload["parental_info"] = {"parent_task_id": parent_id}
                response = requests.post(url, headers=headers, json=task_payload)
            else:
                url = f"https://projectsapi.zoho.in/api/v3/portal/{PORTAL_ID}/projects/{PROJECT_ID}/tasks"
                response = requests.post(url, headers=headers, json=task_payload)

            if response.status_code in (401, 403):
                token = get_access_token()
                headers["Authorization"] = f"Zoho-oauthtoken {token}"
                response = requests.post(url, headers=headers, json=task_payload)


            if response.status_code not in (200, 201):
                print(f"Zoho Error: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )

            created_tasks.append(response.json())

    return {
        "message": "Tasks created successfully",
        "tasks": created_tasks
    }

@app.get("/tasks")
def get_tasks():

    url = f"https://projectsapi.zoho.in/restapi/portal/{PORTAL_ID}/projects/{PROJECT_ID}/tasks/"
    token = get_valid_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    response = requests.get(url, headers=headers)
    if response.status_code in (401, 403):
        token = get_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {token}"
        response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()

@app.get("/tasks/{task_id}")
def get_task(task_id: str):

    url = f"https://projectsapi.zoho.in/restapi/portal/{PORTAL_ID}/projects/{PROJECT_ID}/tasks/{task_id}/"
    token = get_valid_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}

    response = requests.get(url, headers=headers)
    if response.status_code in (401, 403):
        token = get_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {token}"
        response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Task not found")

    return response.json()


from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
import json
import re

load_dotenv()
app = FastAPI()

# Load env variables
CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")
PORTAL_ID = os.getenv("ZOHO_PORTAL_ID")
PROJECT_ID = os.getenv("ZOHO_PROJECT_ID")
TASKLIST_ID = os.getenv("ZOHO_TASKLIST_ID")
ZOHO_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"


def get_access_token():
    url = "https://accounts.zoho.in/oauth/v2/token"

    payload = {
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": os.getenv("ZOHO_REDIRECT_URI"),
        "grant_type": "refresh_token"
    }

    response = requests.post(url, data=payload)

    if response.status_code != 200:
        print("Zoho Token Error:", response.text)
        raise HTTPException(status_code=401, detail="Failed to get Zoho access token")

    token_data = response.json()
    if "access_token" not in token_data:
        raise HTTPException(status_code=401, detail="Access token not found")

    new_token = token_data["access_token"]
    os.environ["ZOHO_ACCESS_TOKEN"] = new_token
    return new_token



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
    per_page = 400
    
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
    
    Per user request: '8.55h' should be '08:55'.
    This treats '.' as a separator for minutes when hours are specified.
    
    Returns: {"value": "HH:MM", "type": "hours"}
    """
    if duration_raw is None or str(duration_raw).strip() == "":
        return None
    
    s = str(duration_raw).strip().lower()
    
    def format_to_zoho_hh_mm(h, m):
        h_int = int(h)
        m_int = int(m)
        return f"{h_int:02d}:{m_int:02d}"

    # 1. Handle HH:MM format
    if ":" in s:
        m_colon = re.match(r"(\d+):(\d+)", s)
        if m_colon:
            return {"value": format_to_zoho_hh_mm(m_colon.group(1), m_colon.group(2)), "type": "hours"}

    # 2. Handle HH.MM format (treating . as minute separator per user request)
    # Match strings like 8.55h, 8.55 h, or just 8.55
    m_dot = re.match(r"(\d+)\.(\d+)\s*(h|hr|hrs|hour|hours)?", s)
    if m_dot:
        return {"value": format_to_zoho_hh_mm(m_dot.group(1), m_dot.group(2)), "type": "hours"}

    # 3. Handle whole numbers with or without unit
    m_h = re.fullmatch(r"(\d+)\s*(h|hr|hrs|hour|hours)?", s)
    if m_h:
        return {"value": format_to_zoho_hh_mm(m_h.group(1), 0), "type": "hours"}
    
    # 4. Handle days (1 day = 8 hours)
    m_d = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(d|day|days)", s)
    if m_d:
        value_days = float(m_d.group(1))
        value_hours_total = value_days * 8
        h = int(value_hours_total)
        m = int(round((value_hours_total - h) * 60))
        return {"value": f"{h:02d}:{m:02d}", "type": "hours"}
    
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


@app.post("/tasks/{google_sheet_name}")
def create_task(google_sheet_name: str):
    # token = get_valid_access_token()
    token = get_access_token()
    print(token, 'new access token')
    
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
        # "1IHBNbK5siAwRIkVKKeLPnd6r4zzNMMwyPZ3cu6THdJM" # original sheet ID
        "1OiANUEPff9V_2PccEGLzExcxb8GhvI1RJLuFh8up1mk" # new sheet ID for testing purpose
    )
    
    # Target a specific sheet as requested (e.g., "18-02")
    print(google_sheet_name, 'google sheet name')
    target_sheet_name = google_sheet_name
    try:
        sheet = spreadsheet.worksheet(target_sheet_name)
        sheets_to_process = [sheet]
        print(f"Processing target sheet: '{target_sheet_name}'")
    except gspread.exceptions.WorksheetNotFound:
        print(f"Sheet '{target_sheet_name}' not found. Falling back to all sheets.")
        sheets_to_process = spreadsheet.worksheets()

    # Fetch all projects and users ONCE from the API
    all_projects = get_all_projects()
    user_map = get_portal_users()

    created_tasks = []
    for sheet in sheets_to_process:
        for sheet_data in sheet.get_all_records():
            # Get project ID
            project_code_raw = str(sheet_data.get('Project code', ''))
            project_key = project_code_raw.split("-")[-1].strip()

            print(project_key, 'project key')
        
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
            duration_raw = str(sheet_data.get("Duration", "")).strip()
            duration_obj = parse_duration_to_duration_object(duration_raw)
            if duration_obj:
                task_payload["duration"] = duration_obj

            billing_type = sheet_data.get("Billing Type", "none")
            if billing_type:
                task_payload["billing_type"] = billing_type

            # Support Name, ID, or Email from "Task Owner" column
            owner_input = str(sheet_data.get("Task Owner", "")).strip().lower()
            print(owner_input)
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
            parent_task_id = sheet_data.get("Task Parent ID")
            if parent_task_id and str(parent_task_id).strip() != "":
                parent_id = str(parent_task_id).strip()
                if not re.match(r"^[0-9]+$", parent_id):
                    # raise HTTPException(status_code=400, detail=f"Invalid Parent_id '{parent_id}'. Provide numeric Zoho task id.")
                    print("Invalid Parent_id-------------------------------", parent_id)
                    continue

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
                # raise HTTPException(
                #     status_code=response.status_code,
                #     detail=response.text
                # )
                print("Zoho Error and task owner.-------------------------------", response.text,owner_input)
                continue

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


# --- NEW GOOGLE SHEETS USER MAPPING API --- #
from typing import Optional

class AddUserRequest(BaseModel):
    sheet_name: str
    name: Optional[str] = None

def get_or_create_uid(raw_name: str):
    """Helper to lookup or generate a new UID permanently."""
    import time
    import random
    
    cleaned_name = str(raw_name).strip()
    if not cleaned_name:
        return None
        
    CUSTOM_MAP_FILE = "custom_users.json"
    user_map = {}
    if os.path.exists(CUSTOM_MAP_FILE):
        try:
            with open(CUSTOM_MAP_FILE, "r") as f:
                user_map = json.load(f)
        except Exception:
            pass
            
    lookup = cleaned_name.lower()
    if lookup in user_map:
        return user_map[lookup]
        
    new_uid = str(int(time.time() * 1000)) + str(random.randint(100000, 999999))
    user_map[lookup] = new_uid
    
    with open(CUSTOM_MAP_FILE, "w") as f:
        json.dump(user_map, f, indent=4)
        
    return new_uid

@app.post("/add-user")
def add_user_to_sheet(request: AddUserRequest):
    """
    1. COMPULSORY: Always scans existing names in the sheet and backfills missing UIDs.
    2. OPTIONAL: Appends a brand new user row if 'name' is provided in the request.
    """
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("1OiANUEPff9V_2PccEGLzExcxb8GhvI1RJLuFh8up1mk")
        
        try:
            sheet = spreadsheet.worksheet(request.sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            raise HTTPException(status_code=404, detail=f"Worksheet '{request.sheet_name}' not found.")
            
        # Get exact column coordinates
        headers = sheet.row_values(1)
        headers_lower = [str(h).strip().lower() for h in headers]
        try:
            name_col_idx = headers_lower.index("employee name") + 1
            uid_col_idx = headers_lower.index("unique id") + 1
        except ValueError:
            raise HTTPException(status_code=400, detail="Missing 'Employee Name' or 'Unique ID' header in Row 1")

        # Download all data to find gaps
        all_data = sheet.get_all_values()
        updates_made = 0
        
        # --- FEATURE 1: COMPULSORY BACKFILL CHECK --- #
        # Loop through existing rows (skip row 1 which is headers)
        for row_index_0_based, row_data in enumerate(all_data[1:]):
            row_index = row_index_0_based + 2 # 1-based indexing for gspread
            
            # Safely extract name and uid cells no matter how short the row is
            cell_name = row_data[name_col_idx - 1].strip() if len(row_data) >= name_col_idx else ""
            cell_uid = row_data[uid_col_idx - 1].strip() if len(row_data) >= uid_col_idx else ""
            
            # Condition: If name exists, but UID is completely empty
            if cell_name and not cell_uid:
                fresh_uid = get_or_create_uid(cell_name)
                # Physically inject the UID into the existing blank cell
                sheet.update_cell(row_index, uid_col_idx, fresh_uid)
                updates_made += 1

        # --- FEATURE 2: APPEND NEW USER (IF PROVIDED) --- #
        new_user_appended = False
        appended_uid = None
        
        if request.name and str(request.name).strip():
            new_name = str(request.name).strip()
            appended_uid = get_or_create_uid(new_name)
            
            # Find the absolute next empty row for the name column
            current_name_col_values = sheet.col_values(name_col_idx)
            next_empty_row = len(current_name_col_values) + 1
            
            sheet.update_cell(next_empty_row, name_col_idx, new_name)
            sheet.update_cell(next_empty_row, uid_col_idx, appended_uid)
            
            new_user_appended = True

        return {
            "message": "Operation Complete",
            "backfilled_existing_users": updates_made,
            "new_user_appended": new_user_appended,
            "appended_name": request.name if new_user_appended else None,
            "appended_uid": appended_uid
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets Error: {str(e)}")


# ============================================================
# --- NEW: COMMENT SYNC & EMAIL REMINDER FEATURE --- #
# ============================================================
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_SENDER_EMAIL = os.getenv("SMTP_SENDER_EMAIL", "")
SMTP_SENDER_PASSWORD = os.getenv("SMTP_SENDER_PASSWORD", "")
COMMENT_DATA_FILE = "comment_data.json"


def load_comment_data() -> dict:
    """Load the user dictionary from comment_data.json."""
    if not os.path.exists(COMMENT_DATA_FILE):
        raise HTTPException(status_code=404, detail=f"'{COMMENT_DATA_FILE}' not found. Please create it first.")
    with open(COMMENT_DATA_FILE, "r") as f:
        return json.load(f)


def send_reminder_email(to_email: str, to_name: str) -> bool:
    """Send a 'comment missing' reminder email. Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Action Required: Your comment is not added in your task"
        msg["From"] = SMTP_SENDER_EMAIL
        msg["To"] = to_email

        body = f"""Hi {to_name},

This is a gentle reminder that your comment has not been added to your assigned task yet.

Please log into the system and add your comment at your earliest convenience.

Thanks,
Creole Studios Team"""

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_SENDER_EMAIL, SMTP_SENDER_PASSWORD)
            server.sendmail(SMTP_SENDER_EMAIL, to_email, msg.as_string())

        print(f"[Email] Sent reminder to {to_name} at {to_email}")
        return True

    except Exception as e:
        print(f"[Email Error] Failed to send to {to_email}: {e}")
        return False


@app.post("/sync-comments/{sheet_name}")
def sync_comments(sheet_name: str):
    """
    Reads comment_data.json and syncs Hours + Is Commented into the Google Sheet.
    - For each name found in the sheet, fills in their hours and comment status.
    - If is_commented is False, sends a reminder email to their address.
    - If the email is sent successfully, writes 'Email Sent' in the 'Email Sent Status' column.
    """
    # Load the user dictionary
    comment_data = load_comment_data()

    # Build a quick lookup: lowercase name -> user dict
    name_lookup = {v["name"].lower(): v for v in comment_data.values()}

    # Connect to Google Sheets (reuse existing auth pattern)
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key("1OiANUEPff9V_2PccEGLzExcxb8GhvI1RJLuFh8up1mk")

    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"Worksheet '{sheet_name}' not found.")

    # Read headers from row 1 and find the required columns
    raw_headers = sheet.row_values(1)
    headers_lower = [h.strip().lower() for h in raw_headers]

    def col_idx(name: str):
        """Returns 1-based column index for the given header name (case-insensitive)."""
        try:
            return headers_lower.index(name.lower()) + 1
        except ValueError:
            return None

    name_col = col_idx("name")
    hours_col = col_idx("hours")
    is_commented_col = col_idx("is commented")
    email_status_col = col_idx("email sent status")

    if not name_col:
        raise HTTPException(status_code=400, detail="'Name' column not found in the sheet header row.")

    # Read all values
    all_rows = sheet.get_all_values()

    results = []
    batch_updates = []          # Collect all cell changes here first
    email_status_writes = []    # Track email-sent rows separately (written after emails sent)

    for row_idx_0, row in enumerate(all_rows[1:], start=2):  # Skip header, 1-based row index
        # Get the name from the Name column (handle short rows safely)
        cell_name = row[name_col - 1].strip() if len(row) >= name_col else ""
        if not cell_name:
            continue  # Skip blank rows

        user = name_lookup.get(cell_name.lower())
        if not user:
            print(f"[Skip] '{cell_name}' not found in comment_data.json")
            continue

        # --- Queue Hours update ---
        if hours_col:
            hours_value = user["hours"]
            hours_str = json.dumps(hours_value) if isinstance(hours_value, dict) else str(hours_value)
            batch_updates.append({
                "range": gspread.utils.rowcol_to_a1(row_idx_0, hours_col),
                "values": [[hours_str]]
            })

        # --- Queue Is Commented update ---
        comment_value = "True" if user["is_commented"] else "False"
        if is_commented_col:
            batch_updates.append({
                "range": gspread.utils.rowcol_to_a1(row_idx_0, is_commented_col),
                "values": [[comment_value]]
            })

        # --- Send Email if Not Commented (still per-user, but fast) ---
        email_sent = False
        if not user["is_commented"]:
            email_sent = send_reminder_email(user["email"], user["name"])
            if email_sent and email_status_col:
                email_status_writes.append({
                    "range": gspread.utils.rowcol_to_a1(row_idx_0, email_status_col),
                    "values": [["Email Sent"]]
                })

        results.append({
            "name": user["name"],
            "hours_written": user["hours"],
            "is_commented": user["is_commented"],
            "email_sent": email_sent
        })

    # --- ONE single batch write for all hours + comment values ---
    all_updates = batch_updates + email_status_writes
    if all_updates:
        sheet.batch_update(all_updates)

    return {
        "message": "Sync complete!",
        "sheet": sheet_name,
        "processed": results
    }

# 🚀 Automated Zoho Task Functionality

> **A powerful FastAPI-powered automation engine that bridges Zoho Projects, Google Sheets, and Gmail — turning your manual workflows into a single API call!**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![Zoho Projects](https://img.shields.io/badge/Zoho-Projects%20API-red)](https://www.zoho.com/projects/)
[![Google Sheets](https://img.shields.io/badge/Google-Sheets%20API-brightgreen?logo=google-sheets)](https://developers.google.com/sheets)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ What Does This Do?

This project automates three powerful workflows — all from a single FastAPI server:

| # | Feature | Description |
|---|---------|-------------|
| 🗂️ | **Task Creator** | Reads task data from a Google Sheet and bulk-creates tasks in Zoho Projects via the API |
| 👤 | **User Mapper** | Scans a Google Sheet, generates unique employee IDs, and backfills them automatically |
| 📧 | **Comment Sync & Email Reminder** | Reads a user database, updates comment/hours status in the sheet, and auto-emails users who haven't commented |

---

## 🏗️ Architecture Overview

```
Google Sheet  ──►  FastAPI Server  ──►  Zoho Projects API
                        │
                        ├──►  Google Sheets API (Read/Write)
                        │
                        └──►  Gmail SMTP (Email Reminders)
```

---

## ⚡ Features

### 📋 1. Zoho Task Creator — `POST /tasks/{sheet_name}`
- Reads rows from a specified Google Sheet tab
- Dynamically resolves **Project Codes** to Zoho Project IDs (with pagination support)
- Resolves **Task Owners** by name, email, or ID from a local user registry
- Supports **Parent-Child Tasks** via `Task Parent ID` column
- Supports `Duration`, `Billing Type`, and more
- Handles token refresh automatically on 401/403 errors

### 🙋 2. User ID Manager — `POST /add-user`
- **Backfills** missing Unique IDs for existing employees in the sheet automatically — every single time it runs!
- **Appends** new employees optionally with a freshly generated Unique ID
- IDs are persisted to a local `custom_users.json` database so they never change

### 📧 3. Comment Sync + Email Alerts — `POST /sync-comments/{sheet_name}`
- Reads a local `comment_data.json` user database
- For each employee found in the Google Sheet:
  - ✅ Writes their **hours breakdown** (`{"non_billable_hours": "...", "billable_hours": "..."}`)
  - ✅ Writes their **comment status** (`True` / `False`)
  - 📩 **Sends an automated Gmail reminder** if their comment is `False`
  - 📌 **Marks "Email Sent"** in the sheet for full audit trail
- Uses **batch updates** — writes ALL sheet changes in a single API call for maximum speed

---

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.10+
- A [Zoho Projects](https://www.zoho.com/projects/) account with API access
- A [Google Cloud](https://console.cloud.google.com/) Service Account with Sheets + Drive API enabled
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) generated

### 2. Clone the Repository

```bash
git clone https://github.com/Supershivam07/Automated-zoho-task-functionality.git
cd Automated-zoho-task-functionality
```

### 3. Set Up a Virtual Environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirement.txt
```

### 5. Configure Environment Variables

```bash
cp .env.example .env
```

Then open `.env` and fill in all your credentials (Zoho OAuth, Google Sheets, Gmail SMTP).

### 6. Add Your Google Service Account

Place your `credentials.json` (Google Service Account key file) in the project root. **Never commit this file.**

### 7. Set Up Your Data Files

```bash
# Create your user sync database from the example
cp comment_data.example.json comment_data.json
# Edit comment_data.json with your real user data
```

### 8. Run the Server

```bash
uvicorn main:app --reload
```

Open **[http://localhost:8000/docs](http://localhost:8000/docs)** to explore the interactive API!

---

## 📊 Google Sheet Structure

### For Task Creation (`/tasks/{sheet_name}`)
| Column | Required | Description |
|--------|----------|-------------|
| `Title` | ✅ | Task name |
| `Description` | ✅ | Task description |
| `Project code` | ✅ | Zoho project key (e.g. `255`) |
| `Task Owner` | ❌ | Name, email, or Zoho ID |
| `Duration` | ❌ | e.g. `8h`, `1.5d`, `08:30` |
| `Billing Type` | ❌ | e.g. `billable` |
| `Task Parent ID` | ❌ | 19-digit Zoho parent task ID |

### For User Mapping (`/add-user`)
| Column | Required | Description |
|--------|----------|-------------|
| `Employee Name` | ✅ | Full name of the employee |
| `Unique ID` | ✅ | Auto-generated — leave blank, it fills itself! |

### For Comment Sync (`/sync-comments/{sheet_name}`)
| Column | Required | Description |
|--------|----------|-------------|
| `Name` | ✅ | Employee name (must match `comment_data.json`) |
| `Hours` | ✅ | Auto-filled with hours breakdown JSON |
| `Is Commented` | ✅ | Auto-filled `True` / `False` |
| `Email Sent Status` | ❌ | Auto-filled with `Email Sent` after reminder |

---

## 🔑 Environment Variables Reference

See [`.env.example`](.env.example) for a full template.

| Variable | Description |
|----------|-------------|
| `ZOHO_CLIENT_ID` | Your Zoho API Console Client ID |
| `ZOHO_CLIENT_SECRET` | Your Zoho API Console Client Secret |
| `ZOHO_REFRESH_TOKEN` | OAuth Refresh Token (offline access) |
| `ZOHO_PORTAL_ID` | Your Zoho Portal numeric ID |
| `ZOHO_PROJECT_ID` | Default Zoho Project ID |
| `ZOHO_REDIRECT_URI` | OAuth redirect URI (e.g. `http://localhost:8000/callback`) |
| `SMTP_SENDER_EMAIL` | Gmail address to send reminders from |
| `SMTP_SENDER_PASSWORD` | Gmail App Password (16-char, NOT your regular password!) |

---

## 🔐 Security Notes

- ✅ `.env` is excluded from Git
- ✅ `credentials.json` is excluded from Git
- ✅ `comment_data.json` (contains emails) is excluded from Git
- ✅ All test/debug scripts are excluded from Git
- 📄 Use `.env.example` and `comment_data.example.json` as safe references

---

## 📁 Project Structure

```
📦 Automated-zoho-task-functionality
 ┣ 📜 main.py                    # All FastAPI routes and business logic
 ┣ 📜 requirement.txt            # Python dependencies
 ┣ 📄 .env.example               # Environment variable template (safe to commit)
 ┣ 📄 comment_data.example.json  # User data template (safe to commit)
 ┣ 📄 .gitignore                 # Excludes sensitive files
 ┗ 📖 README.md                  # You are here!
```

---

## 🧠 How the Zoho OAuth Flow Works

1. Register your app at [Zoho API Console](https://api-console.zoho.in/)
2. Set scopes: `ZohoProjects.portals.READ`, `ZohoProjects.projects.ALL`, `ZohoProjects.tasks.ALL`, `ZohoProjects.tasks.CREATE`
3. Generate a **Self Client** authorization code
4. Exchange it for a **Refresh Token** and store it in `.env`
5. The server auto-refreshes the access token on every request — zero manual intervention!

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you'd like to change.

---

## 📬 Contact

Built with ❤️ at **Creole Studios**

---

*If this project saved you hours of manual work, consider giving it a ⭐ on GitHub!*

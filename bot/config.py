# import os
# from dotenv import load_dotenv

# load_dotenv()

# def get_admin_ids():
#     raw_admins = os.getenv("ADMINS", "")
#     return [int(a.strip()) for a in raw_admins.split(",") if a.strip().isdigit()]

# BOT_TOKEN = os.getenv("BOT_TOKEN")
# API_URL = os.getenv("API_URL", "http://api:8000")
# ADMINS = get_admin_ids()

import os
from dotenv import load_dotenv

load_dotenv()

def get_admin_ids():
    raw_admins = os.getenv("ADMINS", "")
    return [int(a.strip()) for a in raw_admins.split(",") if a.strip().isdigit()]

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL", "http://localhost:8000")  # Изменено для Railway
ADMINS = get_admin_ids()
# Follow up script that polls Gmail inbox 250 emails at a time. 
# Finds confirmation emails from brokers and then updates SQLite to mark those emails as confirmed

import os
import base64
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv
from tracker import get_pending, update_status, get_sent_brokers, get_earliest_sent_date, update_status, log_confirmation

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
TOKEN_PATH = os.path.join(os.path.dirname(__file__), '..', 'token.json')
SCREENSHOTS_PATH = os.path.join(os.path.dirname(__file__), '..', 'screenshots')
SUCCESS_KEYWORDS = ['success', 'removed', 'confirmed', 'opt-out', 'unsubscribe', 'deleted', 'processed']
CONFIRMATION_LINK_KEYWORDS = ['confirm', 'verify', 'optout', 'opt-out', 'unsubscribe', 'remove']

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

# Search for link in email body
def find_confirmation_link(email_body, broker_domain):
    soup = BeautifulSoup(email_body, 'html.parser')
    links = soup.find_all('a', href=True)
    for link in links:
        href = link['href'].lower()
        link_text = link.get_text().lower()
        if broker_domain.lower() in href:
            if any(keyword in href or keyword in link_text for keyword in CONFIRMATION_LINK_KEYWORDS):
                return link['href']
    return None

def click_confirmation_link(url, broker_id, broker_name):
    os.makedirs(SCREENSHOTS_PATH, exist_ok=True)
    with sync_playwright() as p: # using playwright so I can monitor the activity
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(url, wait_until='networkidle', timeout=30000)
            page_text = page.inner_text('body').lower()
            if any(keyword in page_text for keyword in SUCCESS_KEYWORDS):
                print(f"{broker_name} confirmed successful!")
                log_confirmation(broker_id)
            else:
                # none of the success keywords were found so we're less confident about it
                # still marking as successful but we are taking a screenshot for manual reveiw
                screenshot_filename = f"{broker_id}_{datetime.now().strftime('%Y-%m-%d')}.png"
                screenshot_path = os.path.join(SCREENSHOTS_PATH, screenshot_filename)
                page.screenshot(path=screenshot_path)
                print(f"{broker_name} marked successful with low confidence.")
                log_confirmation(broker_id)
        except Exception as e:
            print(f"Failed to load confirmation page for {broker_name}: {e}")
            update_status(broker_id, 'failed')
        finally:
            browser.close()
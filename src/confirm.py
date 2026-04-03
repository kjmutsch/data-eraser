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
from dotenv import load_dotenv
from tracker import update_status, get_sent_brokers, get_earliest_sent_date, log_confirmation

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

def get_email_body(message):
    # gmail api returns emails in parts, look for html
    payload = message.get('payload', {})
    parts = payload.get('parts', [])

    for part in parts:
        if part.get('mimeType') == 'text/html':
            data = part.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8')
    
    body_data = payload.get('body', {}).get('data', '')
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode('utf-8')
    
    return None

def get_sender_domain(message):
    headers = message.get('payload', {}).get('headers', [])
    for header in headers:
        if header['name'].lower() == 'from':
            from_value = header['value']
            if '@' in from_value:
                email_part = from_value.split('@')[-1]
                domain = email_part.split('>')[0].strip().lower()
                return domain
    return None

def run(dry_run=False):
    service = get_gmail_service()
    sent_brokers = get_sent_brokers()
    earliest_date = get_earliest_sent_date()

    if not sent_brokers:
        print("No sent brokers found, exiting.  Run the send script first to populate sent brokers.")
        return
    
    if not earliest_date:
        print("No sent dates found, exiting.  Run the send script first to populate sent brokers with dates.")
        return
    
    broker_by_domain = {broker['domain']: broker for broker in sent_brokers if broker['domain']}

    # search gmail inbox for emails with the data-eraser label that i set up in my inbox and that are after
    # the earliest sent date in the database (so we don't pull emails from before we started sending)
    query = f"label:data-eraser after:{earliest_date}"
    print(f"Searching Gmail with query: {query}")

    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No confirmation emails found.")
        return
    
    print(f"Found {len(messages)} confirmation emails, processing...")

    if dry_run:
        matched = 0
        unmatched = 0
        for message_ref in messages:
            message = service.users().messages().get(
                userId='me',
                id=message_ref['id'],
                format='full'
            ).execute()
            sender_domain = get_sender_domain(message)
            if sender_domain and broker_by_domain.get(sender_domain):
                matched += 1
                print(f"  ✓ Match found: {sender_domain}")
            else:
                unmatched += 1
                print(f"  ? No broker match: {sender_domain}")
        print(f"\nDry run complete. {matched} matched, {unmatched} unmatched out of {len(messages)} emails.")
        return

    for message_ref in messages:
        # fetch the full message details
        message = service.users().messages().get(
            userId='me', 
            id=message_ref['id'],
            format='full'
        ).execute()
        
        sender_domain = get_sender_domain(message)
        if not sender_domain:
            print(f"Could not extract sender domain from email with id {message_ref['id']}, skipping.")
            continue

        matching_broker = broker_by_domain.get(sender_domain)
        if not matching_broker:
            print(f"No matching broker found for sender domain {sender_domain} in email with id {message_ref['id']}, skipping.")
            continue

        broker_id = matching_broker['broker_id']
        broker_name = matching_broker['broker_name']
        print(f"Processing confirmation email from {sender_domain} for broker {broker_name}")

        email_body = get_email_body(message)
        if not email_body:
            print(f"Could not extract email body from email with id {message_ref['id']}, skipping.")
            update_status(broker_id, 'failed')
            continue
        else:
            confirmation_link = find_confirmation_link(email_body, sender_domain)
            if confirmation_link:
                click_confirmation_link(confirmation_link, broker_id, broker_name)
            else:
                print(f"Could not find confirmation link in email from {sender_domain} for broker {broker_name}, marking as failed.")
                update_status(broker_id, 'needs_manual')

        # mark email as read no matter what
        service.users().messages().modify(
            userId='me',
            id=message_ref['id'],
            body = {'removeLabelIds': ['UNREAD']}
        ).execute()

if __name__ == "__main__":
    import sys
    run(dry_run='--dry-run' in sys.argv)
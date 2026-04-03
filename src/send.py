# First script to run that actually sends the email blast and playwright form submissions then logs everything to SQLite
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tracker import init_db
# Load environment variables
from dotenv import load_dotenv
from jinja2 import Template
from tracker import get_pending, update_status, log_request
import time
import yaml

load_dotenv()

# get environment variables
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465)) # default to 465 if not set
TEMPLATE = os.getenv('TEMPLATE')
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
FIRST_NAME = os.getenv('FIRST_NAME')
LAST_NAME = os.getenv('LAST_NAME')
ADDRESS = os.getenv('ADDRESS')
CITY = os.getenv('CITY')
STATE = os.getenv('STATE')
ZIP = os.getenv('ZIP')
PHONE = os.getenv('PHONE')
DOB = os.getenv('DOB')

def render_template(template_str, user_info):
    # using jinja2 to swap in user field'
    template = Template(template_str)
    return template.render(**user_info)

def send_email(address, subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = address
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(EMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"Email sent to {address}")
        return True
    except Exception as e:
        print(f"Failed to send email to {address}: {e}")
        return False
    
def run(dry_run=False):
    brokers_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'brokers.yaml')
    with open(brokers_path, 'r') as f:
        brokers_data = yaml.safe_load(f)

    # mark everything as pending in the database first, then we will update to sent, confirmed, failed, or needs_manual as we go through the list and attempt to send emails or submit forms
    # this way when we continue the script the next day it won't repeat ones already done
    for broker in brokers_data:
        log_request(
            broker_id=broker['id'],
            broker_name=broker['name'],
            method=broker['method'],
            status='pending',
            priority=broker.get('priority', 'medium'),
            opt_out_url=broker.get('opt_out_url'),
            comments=broker.get('comments')
        )

    brokers = get_pending() # tracker helper function

    DAILY_CAP = 250
    sent_today = 0

    # Gather email subject and body (body depends on which template is set, is generic by default)
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', f'{TEMPLATE}.txt')
    with open(template_path, 'r') as f:
        template_str = f.read()
    lines = template_str.split('\n')
    subject = lines[0].replace('Subject: ', '') if lines else f"Data Removal Request for {broker['broker_name']}"
    body = '\n'.join(lines[2:]) if len(lines) > 2 else "Please remove {first_name} {last_name}'s data from your systems."

    for broker in brokers:
        if sent_today >= DAILY_CAP:
            print(f"Daily cap reached, stopping for today. There are {len(brokers) - sent_today} remaining. Run again tomorrow.")
            break

        if broker['method'] == 'form':
            # TODO: hand off to playwright form runner (not yet implemented until we know what the forms look like)
            update_status(broker['broker_id'], 'needs_manual')
            continue

        elif broker['method'] == 'manual':
            update_status(broker['broker_id'], 'needs_manual')
            continue

        # Now render the email template
        user_info = {
            'broker_name': broker['broker_name'],
            'opt_out_url': broker['opt_out_url'],
            'first_name': FIRST_NAME,
            'last_name': LAST_NAME,
            'email': EMAIL_ADDRESS,
            'address': ADDRESS,
            'city': CITY,
            'state': STATE,
            'zip': ZIP,
            'phone': PHONE,
            'dob': DOB
        }

        if dry_run:
            print(f"DRY RUN: Would send email to {broker['broker_name']} with info {user_info}")
            continue

        full_body = render_template(body, user_info)

        # For now we are just using a single generic template, but in the future we can swap this out based on the broker or method
        success = send_email(broker['email'], subject, full_body)

        if success:
            update_status(broker['broker_id'], 'sent')
        else:
            update_status(broker['broker_id'], 'failed')
         
        sent_today += 1
        # sleep for random amount of time between 1-5 seconds to avoid sending too many emails and getting marked as spam
        time.sleep(random.randint(1, 5))

if __name__ == "__main__":
    import sys
    init_db() # tracker helper function to initialize the database if it doesn't exist
    run(dry_run='--dry-run' in sys.argv)
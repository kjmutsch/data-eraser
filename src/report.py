# report.py - reads current SQLite state and sends a summary email
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from dotenv import load_dotenv
from tracker import get_report_data

load_dotenv()

EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465))

def build_report(data):
    successful = data['successful']
    high_priority_issues = data['high_priority_issues']
    lower_priority_issues = data['lower_priority_issues']

    total = len(successful) + len(high_priority_issues) + len(lower_priority_issues)
    successful_count = len(successful)
    needs_attention_count = len(high_priority_issues) + len(lower_priority_issues)
    high_priority_count = len(high_priority_issues)
    low_priority_count = len(lower_priority_issues)
    successful_pct = round((successful_count / total * 100), 1) if total > 0 else 0

    # calculate average response time from brokers that have one
    response_times = [
        broker['response_time_hours']
        for broker in successful
        if broker['response_time_hours'] is not None
    ]
    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 'N/A'

    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'summary_email.html')
    with open(template_path, 'r') as f:
        template_str = f.read()

    template = Template(template_str)
    html = template.render(
        report_date=datetime.now().strftime('%Y-%m-%d %H:%M'),
        total=total,
        successful_count=successful_count,
        successful_pct=successful_pct,
        needs_attention_count=needs_attention_count,
        high_priority_count=high_priority_count,
        low_priority_count=low_priority_count,
        avg_response_time=avg_response_time,
        successful=successful,
        high_priority_issues=high_priority_issues,
        lower_priority_issues=lower_priority_issues
    )
    return html

def send_report(html):
    msg = MIMEMultipart('alternative')
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS
    msg['Subject'] = f"Data Eraser Report — {datetime.now().strftime('%Y-%m-%d')}"
    msg.attach(MIMEText(html, 'html'))
    try:
        # smtp is the same as send.py, but we are sending to ourselves
        # smtp is just a generic email sending protocol
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(EMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"Report sent to {EMAIL_ADDRESS}")
    except Exception as e:
        print(f"Failed to send report: {e}")

def run(dry_run=False):
    data = get_report_data()
    html = build_report(data)

    if dry_run:
        # write to a local html file so you can open it in a browser to preview
        # just for testing purposes
        preview_path = os.path.join(os.path.dirname(__file__), '..', 'report_preview.html')
        with open(preview_path, 'w') as f:
            f.write(html)
        print(f"Dry run complete. Preview saved to {preview_path}")
        print("Open that file in your browser to see what the report looks like.")
        return

    send_report(html)

if __name__ == "__main__":
    import sys
    run(dry_run='--dry-run' in sys.argv)
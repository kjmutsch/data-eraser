import os
import re
import yaml
from urllib.parse import urlparse

def get_domain_from_url(url):
    if not url:
        return None
    if not re.match(r"https?://", url):
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return host.lower().lstrip("www.")

def get_domain_from_email(email):
    if not email:
        return None
    parts = email.split("@")
    if len(parts) == 2:
        return parts[1].lower()
    return None

root = os.path.abspath(os.path.dirname(__file__))  # project root
yaml_path = os.path.join(root, "data", "brokers.yaml")

if not os.path.exists(yaml_path):
    raise FileNotFoundError(f"Expected brokers.yaml at {yaml_path}")

with open(yaml_path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

brokers = data.get("brokers", [])
updated = 0

for broker in brokers:
    if broker.get("domain"):
        continue
    domain = get_domain_from_url(broker.get("website"))
    if not domain:
        domain = get_domain_from_email(broker.get("email"))
    if domain:
        broker["domain"] = domain
        updated += 1

with open(yaml_path, "w", encoding="utf-8") as f:
    yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

print(f"Updated {updated} broker(s) with domain")
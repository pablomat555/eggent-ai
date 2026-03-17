import os
import sys
import json
import requests
import argparse

def main():
    parser = argparse.ArgumentParser(description="Send note to n8n Obsidian Inbox")
    parser.add_argument("--title", required=True, help="Note title")
    parser.add_argument("--content", required=True, help="Note content")
    parser.add_argument("--metadata", required=True, help="JSON string with tags and project")
    args = parser.parse_args()

    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    secret_token = os.getenv("N8N_WEBHOOK_SECRET")

    if not webhook_url or not secret_token:
        print("Error: N8N_WEBHOOK_URL or N8N_WEBHOOK_SECRET is missing in environment.")
        sys.exit(1)

    try:
        metadata_dict = json.loads(args.metadata)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in metadata.")
        sys.exit(1)

    payload = {
        "title": args.title,
        "content": args.content,
        "metadata": metadata_dict
    }

    headers = {
        "Content-Type": "application/json",
        "X-Writer-Token": secret_token
    }

    try:
        response = requests.post(webhook_url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        print(f"✅ Success: Webhook triggered. Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error sending webhook: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
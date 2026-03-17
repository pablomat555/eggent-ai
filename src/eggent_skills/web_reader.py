import argparse
import sys
import os
import requests
from loguru import logger
from typing import Any

logger.remove()
logger.add(sys.stderr, level="INFO")

# Исправлен порт на 11235
CRAWL4AI_ENDPOINT = "http://crawl4ai:11235/crawl"

def fetch_markdown(url: str) -> str | None:
    api_token = os.getenv("CRAWL4AI_API_TOKEN", "")
    headers: dict[str, str] = {
        "Content-Type": "application/json"
    }
    
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    # Исправлено: API требует массив 'urls'
    payload: dict[str, Any] = {
        "urls": [url],
        "bypass_cache": True,
        "extract_blocks": True,
        "word_count_threshold": 10
    }

    try:
        logger.info(f"Requesting Crawl4AI: {url}")
        response = requests.post(CRAWL4AI_ENDPOINT, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        
        if "results" in data and isinstance(data["results"], list) and len(data["results"]) > 0:
            return data["results"][0].get("markdown", "")
        return data.get("markdown", "")

    except Exception as e:
        logger.error(f"Crawl API Error: {e}")
        return None

def main() -> None:
    parser = argparse.ArgumentParser(description="Web Reader for Eggent")
    parser.add_argument("--url", type=str, required=True, help="Target URL to extract")
    args = parser.parse_args()

    markdown_result = fetch_markdown(args.url)

    if markdown_result and markdown_result.strip():
        print(markdown_result)
        sys.exit(0)
    else:
        logger.error(f"Failed to extract content from: {args.url}")
        print(f"Error: Content could not be extracted from {args.url}")
        sys.exit(1)

if __name__ == "__main__":
    main()
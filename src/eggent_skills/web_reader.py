import argparse
import sys
import os
import requests
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

CRAWL4AI_ENDPOINT = "http://crawl4ai:11235/crawl"

def fetch_markdown(url: str) -> str | None:
    api_token = os.getenv("CRAWL4AI_API_TOKEN", "")
    headers = {"Content-Type": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    payload = {
        "urls": [url],
        "bypass_cache": True,
        "extract_blocks": True,
        "word_count_threshold": 10,
    }

    try:
        logger.info(f"Requesting Crawl4AI: {url}")
        response = requests.post(
            CRAWL4AI_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=60,
        )

        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Response text: {response.text[:3000]}")

        response.raise_for_status()
        data = response.json()

        # Основной ожидаемый формат
        results = data.get("results")
        if isinstance(results, list) and results:
            result_obj = results[0]

            # если API отдает success/error_message
            if result_obj.get("success") is False:
                logger.error(f"Crawl failed: {result_obj.get('error_message')}")
                return None

            markdown_obj = result_obj.get("markdown")

            if isinstance(markdown_obj, dict):
                fit_md = markdown_obj.get("fit_markdown", "")
                raw_md = markdown_obj.get("raw_markdown", "")
                final_md = fit_md or raw_md
                if final_md and str(final_md).strip():
                    return str(final_md)

            elif isinstance(markdown_obj, str) and markdown_obj.strip():
                return markdown_obj.strip()

        logger.error(f"Unexpected API response format: {data}")
        return None

    except requests.Timeout:
        logger.error("Crawl API timeout")
        return None
    except requests.RequestException as e:
        logger.error(f"HTTP error: {e}")
        return None
    except ValueError as e:
        logger.error(f"JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected Crawl API error: {e}")
        return None

def main() -> None:
    parser = argparse.ArgumentParser(description="Web Reader for Eggent")
    parser.add_argument("--url", type=str, required=True, help="Target URL to extract")
    args = parser.parse_args()

    markdown_result = fetch_markdown(args.url)

    if markdown_result and markdown_result.strip():
        print(markdown_result.strip())
        sys.exit(0)

    logger.error(f"Failed to extract content from: {args.url}")
    print(f"Error: Content could not be extracted from {args.url}")
    sys.exit(1)

if __name__ == "__main__":
    main()
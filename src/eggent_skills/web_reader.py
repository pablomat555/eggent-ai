import argparse
import sys
import os
import requests
from loguru import logger
from typing import Any

# Отключаем дефолтный логгер и направляем логи в stderr, 
# чтобы в stdout (для агента) попадал ТОЛЬКО чистый Markdown.
logger.remove()
logger.add(sys.stderr, level="INFO")

# URL внутреннего сервиса внутри Docker-сети
CRAWL4AI_ENDPOINT = "http://crawl4ai:11225/crawl"

def fetch_markdown(url: str) -> str | None:
    """Отправляет URL в изолированный контейнер Crawl4AI и возвращает Markdown."""
    
    api_token = os.getenv("CRAWL4AI_API_TOKEN", "")
    headers: dict[str, str] = {
        "Content-Type": "application/json"
    }
    
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    payload: dict[str, Any] = {
        "url": url,
        "bypass_cache": True,
        "extract_blocks": True, # Очистка от мусора
        "word_count_threshold": 10
    }

    try:
        logger.info(f"Requesting Crawl4AI: {url}")
        # Таймаут увеличен, так как рендеринг JS может занимать время
        response = requests.post(CRAWL4AI_ENDPOINT, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        
        # Разбор ответа (Crawl4AI может возвращать массив results или сразу объект)
        if "results" in data and isinstance(data["results"], list) and len(data["results"]) > 0:
            return data["results"][0].get("markdown", "")
        
        return data.get("markdown", "")

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error: Crawl4AI took too long to respond for {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing Crawl4AI response: {e}")
        return None

def main() -> None:
    parser = argparse.ArgumentParser(description="Web Reader for Eggent (Crawl4AI Node)")
    parser.add_argument("--url", type=str, required=True, help="Target URL to extract")
    args = parser.parse_args()

    markdown_result = fetch_markdown(args.url)

    if markdown_result and markdown_result.strip():
        # Вывод результата строго в stdout для захвата агентом через Code Execution
        print(markdown_result)
        sys.exit(0)
    else:
        logger.error(f"Failed to extract meaningful content from: {args.url}")
        print(f"Error: Content could not be extracted from {args.url}")
        sys.exit(1)

if __name__ == "__main__":
    main()
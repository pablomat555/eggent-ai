import os
import sys
import json
import requests
import argparse

def normalize_zero_links(items: list[str]) -> list[str]:
    """Очищает список Zero-links от лишних скобок, пустых строк и дубликатов."""
    result = []
    seen = set()
    for item in items:
        if not item or not isinstance(item, str):
            continue
        clean_item = item.replace("[[", "").replace("]]", "").strip()
        if not clean_item:
            continue
        normalized = f"[[{clean_item}]]"
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result

def normalize_tags(tags: list[str]) -> list[str]:
    """Дедуплицирует теги и гарантирует наличие системного тега inbox без дублей."""
    clean_tags = [t.strip() for t in tags if isinstance(t, str) and t.strip()]
    result = []
    seen = set()
    
    for t in clean_tags:
        if t not in seen:
            seen.add(t)
            result.append(t)
            
    if "inbox" not in seen:
        result.insert(0, "inbox")
        
    return result

def build_final_markdown(title: str, content: str, zero_links: list[str], source_url: str) -> str:
    """Собирает финальную структуру Markdown по Master Template."""
    rebuilt = f"-----\n## {title}\n-----\n\n{content.strip()}\n\n"
    
    rebuilt += "---\n## Zero-links\n---\n"
    if zero_links:
        rebuilt += "\n".join(f"- {zl}" for zl in zero_links) + "\n"
    else:
        rebuilt += "- [[Inbox]]\n"
        
    if source_url:
        rebuilt += "\n---\n## Links\n---\n"
        rebuilt += f"- [Source]({source_url})\n"
        
    return rebuilt

def main():
    parser = argparse.ArgumentParser(description="Send note to n8n Obsidian Inbox")
    parser.add_argument("--title", required=True, help="Note title")
    parser.add_argument("--content", required=True, help="Note raw content")
    parser.add_argument("--metadata", required=True, help="JSON string with strict contract data")
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

    # 1. Извлечение данных по контракту
    status = metadata_dict.get("status", "normal")
    source_url = metadata_dict.get("source_url", "")
    raw_tags = metadata_dict.get("tags", [])
    raw_zl = metadata_dict.get("zero_links", [])
    error_text = metadata_dict.get("error_text", "Сетевая ошибка / Timeout")

    # 2. Нормализация тегов
    metadata_dict["tags"] = normalize_tags(raw_tags if isinstance(raw_tags, list) else [raw_tags])

    # 3. Маршрутизация статусов (Fast-Paths & Normal)
    if status == "paywalled":
        body_text = "Краткое описание страницы скрыто пейволом.\n\nСтатус: Paywalled"
        final_zl = ["[[Author]]", "[[Platform]]"]
    elif status == "unavailable":
        body_text = f"Ошибка доступа к странице:\n{error_text}\n\nСтатус: Unavailable"
        final_zl = ["[[Error]]"]
    else:
        # normal
        body_text = args.content
        final_zl = normalize_zero_links(raw_zl)

    # 4. Сборка финального контента
    clean_content_body = build_final_markdown(args.title, body_text, final_zl, source_url)

    # 5. Подготовка Payload
    payload = {
        "title": args.title,
        "content": clean_content_body,
        "metadata": {
            "tags": metadata_dict["tags"]
            # Остальные системные ключи можно не передавать в n8n, если они нужны только для сборки,
            # но оставляем для гибкости (например, если n8n их логирует)
        }
    }

    headers = {
        "Content-Type": "application/json",
        "X-Writer-Token": secret_token
    }

    # 6. Отправка
    try:
        response = requests.post(webhook_url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        print(f"✅ Success: Webhook triggered. Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error sending webhook: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
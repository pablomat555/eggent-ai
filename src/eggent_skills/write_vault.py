from __future__ import annotations
import os
import sys
import json
import requests
import argparse
import re
import yaml
from datetime import datetime

DOMAIN_WHITELIST = {"ai", "trading", "finance", "dev", "english", "obsidian", "automation"}
TYPE_WHITELIST = {"system", "note", "project", "article", "reference", "meeting", "person", "log", "inbox"}

def classify_unprefixed_tag(tag: str) -> str:
    """Классифицирует тег без префикса по вайтлистам."""
    if tag in TYPE_WHITELIST:
        return f"type/{tag}"
    if tag in DOMAIN_WHITELIST:
        return f"domain/{tag}"
    return f"entity/{tag}"

def normalize_zero_links(items: list[str]) -> list[str]:
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

def normalize_tags(tags: list[str], is_new_inbox: bool = False) -> list[str]:
    """
    Нормализация тегов: lowercase, trim, dedupe, prefixing.
    is_new_inbox: Если True, гарантирует наличие тега type/inbox.
    """
    seen = set()
    result = []

    for raw_tag in tags:
        if not isinstance(raw_tag, str):
            continue

        t = raw_tag.strip().lower()
        if not t:
            continue

        # Убираем лишние пробелы вокруг слеша
        t = re.sub(r'\s*/\s*', '/', t)

        # Игнорируем теги-даты (например, 2026/mar)
        if re.match(r'^\d{4}/[a-zа-я]+$', t):
            normalized = t
        elif t.startswith(("domain/", "entity/", "type/")):
            normalized = t
        else:
            normalized = classify_unprefixed_tag(t)

        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    # Гарантируем type/inbox ТОЛЬКО если это запрошено контрактом (is_new_inbox)
    if is_new_inbox and "type/inbox" not in seen and "inbox" not in seen:
        result.insert(0, "type/inbox")
        seen.add("type/inbox")

    return result

def sanitize_title(title: str) -> str:
    """Очищает заголовок от переносов строк и лишних пробелов для Markdown body."""
    return re.sub(r'\s+', ' ', title).strip()

def build_final_markdown(title: str, content: str, zero_links: list[str], source_url: str, tags: list[str]) -> str:
    """Собирает 100% файла: от безопасного YAML до футера."""
    now = datetime.now()
    created_date = now.strftime("%Y-%m-%d %H:%M")
    month_tag = now.strftime("%Y/%b")
    
    clean_title = sanitize_title(title)
    
    # Сборка структуры для YAML
    final_tags = [month_tag]
    for t in tags:
        if t and t != month_tag:
            final_tags.append(t)

    frontmatter = {
        "aliases": [clean_title],
        "tags": final_tags,
        "author": ["Я"],
        "created": created_date
    }
    
    if source_url:
        frontmatter["source_url"] = source_url

    # 1. Безопасная генерация YAML
    yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    # 2. Сборка тела
    rebuilt = f"---\n{yaml_str}---\n\n"
    rebuilt += f"-----\n## {clean_title}\n-----\n\n{content.strip()}\n\n"
    
    # 3. Сборка подвала
    if zero_links:
        rebuilt += "---\n## Zero-links\n---\n"
        rebuilt += "\n".join(f"- {zl}" for zl in zero_links) + "\n"
        
    if source_url:
        rebuilt += "\n---\n## Links\n---\n"
        rebuilt += f"- [Source]({source_url})\n"
        
    return rebuilt

def main():
    parser = argparse.ArgumentParser(description="Send note to n8n Obsidian Inbox")
    parser.add_argument("--title", required=True, help="Note title")
    parser.add_argument("--content", required=True, help="Note raw content")
    parser.add_argument("--metadata", required=True, help="JSON metadata")
    args = parser.parse_args()

    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    secret_token = os.getenv("N8N_WEBHOOK_SECRET")

    if not webhook_url or not secret_token:
        print("Error: N8N_WEBHOOK_URL or N8N_WEBHOOK_SECRET missing.", file=sys.stderr)
        sys.exit(1)

    try:
        metadata_dict = json.loads(args.metadata)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in metadata.", file=sys.stderr)
        sys.exit(1)

    status = metadata_dict.get("status", "normal")
    source_url = metadata_dict.get("source_url", "")
    raw_tags = metadata_dict.get("tags", [])
    raw_zl = metadata_dict.get("zero_links", [])
    error_text = metadata_dict.get("error_text", "Сетевая ошибка / Timeout")
    
    # Читаем флаг is_inbox из метадаты (по умолчанию True для обратной совместимости)
    is_inbox = metadata_dict.get("is_inbox", True)

    clean_tags = normalize_tags(raw_tags if isinstance(raw_tags, list) else [raw_tags], is_new_inbox=is_inbox)

    if status == "paywalled":
        body_text = "Краткое описание страницы скрыто пейволом.\n\nСтатус: Paywalled"
        final_zl = ["[[Author]]", "[[Platform]]"]
    elif status == "unavailable":
        body_text = f"Ошибка доступа к странице:\n{error_text}\n\nСтатус: Unavailable"
        final_zl = ["[[Error]]"]
    else:
        body_text = args.content
        final_zl = normalize_zero_links(raw_zl)

    full_file_content = build_final_markdown(args.title, body_text, final_zl, source_url, clean_tags)

    payload = {
        "title": args.title,
        "content": full_file_content
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
        print(f"❌ Error sending webhook: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
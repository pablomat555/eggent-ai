import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Any

VAULT_PATH = Path("/app/vault")

def parse_frontmatter(yaml_text: str) -> dict:
    """Универсальный мини-парсер: ловит ВСЕ топ-уровневые ключи"""
    meta = {}
    
    # 1. project / domain / author / priority / date и т.д. (однострочные)
    for key in ['project', 'domain', 'author', 'priority', 'date']:
        m = re.search(rf'^{key}:\s*(.+)$', yaml_text, re.MULTILINE)
        if m:
            meta[key] = m.group(1).strip().strip('"\'')
    
    # 2. tags и aliases (и inline, и блочные)
    for key in ['tags', 'aliases']:
        # inline [ ]
        inline = re.search(rf'^{key}:\s*\[(.*?)\]', yaml_text, re.MULTILINE)
        if inline and inline.group(1).strip():
            meta[key] = [t.strip().strip('"\'') for t in inline.group(1).split(',')]
            continue
        
        # блочный список
        block = re.search(rf'^{key}:\s*\n((?:\s*-\s+.*\n?)*)', yaml_text, re.MULTILINE)
        if block:
            lines = block.group(1).strip().split('\n')
            meta[key] = [l.replace('-', '', 1).strip().strip('"\'') for l in lines if l.strip().startswith('-')]
    
    # fallback
    if 'tags' not in meta: meta['tags'] = []
    if 'aliases' not in meta: meta['aliases'] = []
    if 'project' not in meta: meta['project'] = None
    if 'domain' not in meta: meta['domain'] = None
    
    return meta

def search_vault(query: Dict[str, Any]) -> List[Dict]:
    results = []
    max_results = query.get("max_results", 5)
    metadata_filters = query.get("metadata", {})
    text_query = query.get("text")
    filename_pattern = query.get("filename", r".*\.md$")

    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith(".") for part in md_file.parts):
            continue
        if not re.match(filename_pattern, md_file.name, re.IGNORECASE):
            continue

        # ФАЗА 1: только head
        try:
            with md_file.open("r", encoding="utf-8") as f:
                head = f.read(2048)
            fm_match = re.match(r'^---\s*\n(.*?)\n---', head, re.DOTALL)
            if not fm_match:
                continue
            yaml_text = fm_match.group(1)
            meta = parse_frontmatter(yaml_text)
            content_start = fm_match.end()
        except Exception:
            continue

        # Фильтр метаданных (поддержка domain!)
        match = True
        for key, val in metadata_filters.items():
            meta_val = meta.get(key)
            if key == "tags":
                search_tags = val if isinstance(val, list) else [val]
                if not any(t in meta.get("tags", []) for t in search_tags):
                    match = False
                    break
            else:
                if meta_val != val and not re.search(str(val), str(meta_val or ""), re.IGNORECASE):
                    match = False
                    break
        if not match:
            continue

        # ФАЗА 2: полный файл
        with md_file.open("r", encoding="utf-8") as f:
            full_content = f.read()
        text_content = full_content[content_start:].strip()

        extracted = text_content[:2000]
        if text_query:
            text_match = re.search(re.escape(text_query), text_content, re.IGNORECASE)
            if not text_match:
                continue
            start = max(0, text_match.start() - 1000)
            end = min(len(text_content), text_match.end() + 1000)
            extracted = text_content[start:end].strip()
            if start > 0: extracted = "[...до...]\n" + extracted
            if end < len(text_content): extracted += "\n[...после...]"

        title = meta.get("aliases")[0] if meta.get("aliases") else md_file.stem

        results.append({
            "path": str(md_file.relative_to(VAULT_PATH)),
            "title": title,
            "tags": meta.get("tags", []),
            "project": meta.get("project") or "None",
            "domain": meta.get("domain") or "None",
            "content": extracted[:1500]
        })

        if len(results) >= max_results:
            break

    return results

if __name__ == "__main__":
    try:
        query = json.loads(sys.stdin.read().strip())
        result = search_vault(query)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps([{"error": str(e)}]))
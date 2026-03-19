import re
import json
import argparse
import sys
from pathlib import Path
from typing import Any

STOP_WORDS = {
    "что", "как", "где", "когда", "зачем", "почему", "какие", "какой", "какая",
    "в", "на", "с", "по", "к", "о", "об", "и", "а", "но", "да", "для", "от", "до",
    "из", "у", "за", "над", "под", "или", "это", "то", "все", "ли", "мы", "вы",
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for",
    "of", "with", "by", "about", "what", "how", "why", "where", "when", "which"
}

IGNORED_DIRS = {".stversions", ".obsidian", ".git", "__pycache__", ".trash"}

def should_skip_path(path: Path) -> bool:
    """Жесткая фильтрация системных и скрытых директорий."""
    parts = set(path.parts)
    if parts.intersection(IGNORED_DIRS):
        return True
    return any(part.startswith('.') and part != '.' for part in path.parts)

def is_backup_file(filename: str) -> bool:
    """Отсечение versioned copies (например Syncthing: name~20260314-184802.md)."""
    return bool(re.search(r'~\d{8}-\d{6}', filename) or "sync-conflict" in filename.lower())

def _parse_tags(content: str) -> list[str]:
    """Строгий парсинг тегов из YAML frontmatter."""
    tags = []
    yaml_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not yaml_match:
        return tags
    
    yaml_content = yaml_match.group(1)
    tags_match = re.search(r'^tags:\n((?:\s+- .*\n?)*)', yaml_content, re.MULTILINE)
    
    if tags_match:
        for line in tags_match.group(1).split('\n'):
            line = line.strip()
            if line.startswith('-'):
                clean_tag = line[1:].strip().strip('"').strip("'")
                if clean_tag:
                    tags.append(clean_tag)
    return tags

def _extract_h1(content: str) -> str:
    """Извлечение заголовка H1 для fallback-эвристики."""
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    return match.group(1).strip() if match else ""

def _extract_best_snippet(paragraphs: list[str], keywords: list[str]) -> str:
    """Извлечение наиболее релевантного абзаца."""
    candidates = []
    for i, para in enumerate(paragraphs):
        para_lower = para.lower()
        matches = sum(para_lower.count(kw) for kw in keywords)
        
        if matches > 0:
            is_heading = bool(re.match(r'^#{1,6}\s', para.strip()))
            candidates.append((is_heading, matches, para.strip(), i))
            
    if not candidates:
        return "Сниппет не найден, но ключевые слова присутствуют."
        
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_para_index = candidates[0][3]
    best_snippet = paragraphs[best_para_index].strip()
    
    if len(best_snippet) < 200 and best_para_index + 1 < len(paragraphs):
        next_para = paragraphs[best_para_index + 1].strip()
        if next_para and not re.match(r'^---', next_para):
            best_snippet += "\n\n" + next_para
            
    return best_snippet[:800] + "..." if len(best_snippet) > 800 else best_snippet

def _score_and_extract(file_path: Path, content: str, keywords: list[str], candidate_entities: list[str]) -> dict | None:
    """Гибридный скоринг с fallback на H1/Filename для старых заметок."""
    content_lower = content.lower()
    filename_lower = file_path.stem.lower()
    first_200 = content_lower[:200]
    
    raw_tags = _parse_tags(content)
    norm_tags = [t.lower() for t in raw_tags]
    h1_title = _extract_h1(content).lower()
    
    base_score = 0
    entity_score = 0
    entity_matches = []
    
    # --- 1. Base Layer ---
    for kw in keywords:
        if kw in filename_lower:
            base_score += 5
        if kw in first_200:
            base_score += 2
            
    paragraphs = content.split('\n\n')
    for para in paragraphs:
        para_lower = para.lower()
        matches = sum(para_lower.count(kw) for kw in keywords)
        if matches > 0:
            base_score += matches 
            if re.match(r'^#{1,6}\s', para.strip()):
                for kw in keywords:
                    if kw in para_lower:
                        base_score += 3

    # --- 2. Entity Layer (С поддержкой Fallback для заметок без тегов) ---
    for ent_full in candidate_entities:
        kw = ent_full.split('/', 1)[1]
        is_entity_matched = False

        # Точный тег (высший приоритет)
        if ent_full in norm_tags:
            entity_score += 8
            is_entity_matched = True
            
        # Fallback: поиск в H1
        if h1_title and kw in h1_title:
            entity_score += 5
            is_entity_matched = True
            
        # Fallback: поиск в имени файла
        if kw in filename_lower:
            entity_score += 4
            is_entity_matched = True
            
        # Fallback: явное упоминание сущности в других заголовках
        for para in paragraphs:
            if re.match(r'^#{2,6}\s', para.strip()) and kw in para.lower():
                entity_score += 3
                is_entity_matched = True

        if is_entity_matched:
            entity_matches.append(ent_full)

    # --- 3. Anti-Noise Layer ---
    is_direct_target = (entity_score > 0) or all(kw in filename_lower for kw in keywords)
    is_system_file = "type/system" in norm_tags or "system" in norm_tags
    looks_like_prompt = "prompt" in filename_lower or "instruction" in filename_lower or "система" in filename_lower
    
    system_penalty = 0
    if not is_direct_target:
        if is_system_file:
            system_penalty -= 8
        if looks_like_prompt:
            system_penalty -= 4

    total_score = base_score + entity_score + system_penalty

    if total_score > 0 or is_direct_target:
        return {
            "title": file_path.stem,
            "file": file_path.name,
            "path": str(file_path),
            "score": total_score,
            "entity_score": entity_score,
            "entity_matches": list(set(entity_matches)),
            "tags": raw_tags,
            "snippet": _extract_best_snippet(paragraphs, keywords)
        }
    return None

def execute_search(vault_dir: str | Path, query: str) -> dict[str, Any]:
    vault_path = Path(vault_dir)
    if not vault_path.exists() or not vault_path.is_dir():
        print(f"Vault path not found: {vault_path}", file=sys.stderr)
        return {"status": "error", "error_message": "Vault path does not exist", "results": []}

    keywords = [word.lower() for word in query.split() if word.strip() and word.lower() not in STOP_WORDS]
    if not keywords:
        return {"status": "no_results", "message": "Query contains only stop-words or is empty", "results": []}
        
    candidate_entities = [f"entity/{kw}" for kw in keywords]

    # Фильтрация на этапе обхода дерева
    valid_md_files = [
        p for p in vault_path.rglob("*.md")
        if not should_skip_path(p) and not is_backup_file(p.name)
    ]
    
    def search_pass(mode: str) -> list[dict]:
        pass_results = []
        for file_path in valid_md_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                content_lower = content.lower()
                
                if mode == "AND":
                    if not all(kw in content_lower for kw in keywords):
                        continue
                else:
                    if not any(kw in content_lower for kw in keywords):
                        continue
                        
                res = _score_and_extract(file_path, content, keywords, candidate_entities)
                if res:
                    pass_results.append(res)
            except Exception:
                pass
        return pass_results

    results = search_pass("AND")
    if not results and len(keywords) > 1:
        results = search_pass("OR")

    if not results:
        return {"status": "no_results", "results": []}

    # Дедупликация по canonical title (на случай если versioned files как-то проскочили)
    seen_titles = set()
    unique_results = []
    
    # Предварительная сортировка для дедупликации (чтобы брать лучший вариант)
    results.sort(key=lambda x: (-x["entity_score"], -x["score"]))
    
    for res in results:
        canonical_title = re.sub(r'~\d{8}-\d{6}', '', res["title"]).strip().lower()
        if canonical_title not in seen_titles:
            seen_titles.add(canonical_title)
            unique_results.append(res)

    # Финальная детерминированная сортировка
    unique_results.sort(key=lambda x: (-x["entity_score"], -x["score"], x["file"], x["path"]))
    
    return {"status": "ok", "results": unique_results[:3]}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic Obsidian RAG Search")
    parser.add_argument("--query", required=True, help="Текст для поиска")
    parser.add_argument("--dir", default="/app/vault", help="Путь к корню базы знаний внутри контейнера")
    args = parser.parse_args()

    result = execute_search(args.dir, args.query)
    print(json.dumps(result, ensure_ascii=False, indent=2))
import re
import json
import argparse
from pathlib import Path
from typing import Any
from loguru import logger

STOP_WORDS = {
    "что", "как", "где", "когда", "зачем", "почему", "какие", "какой", "какая",
    "в", "на", "с", "по", "к", "о", "об", "и", "а", "но", "да", "для", "от", "до",
    "из", "у", "за", "над", "под", "или", "это", "то", "все", "ли", "мы", "вы",
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for",
    "of", "with", "by", "about", "what", "how", "why", "where", "when", "which"
}

def _parse_tags(content: str) -> list[str]:
    """Строгий парсинг тегов только из блока 'tags:' в YAML frontmatter."""
    tags = []
    yaml_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not yaml_match:
        return tags
    
    yaml_content = yaml_match.group(1)
    tags_match = re.search(r'^tags:\n((?:\s+- .*\n?)*)', yaml_content, re.MULTILINE)
    
    if tags_match:
        tag_lines = tags_match.group(1).split('\n')
        for line in tag_lines:
            line = line.strip()
            if line.startswith('-'):
                tags.append(line[1:].strip())
    return tags

def _extract_best_snippet(paragraphs: list[str], keywords: list[str]) -> str:
    """Извлечение сниппета: захватывает лучший абзац + следующий, если контекст короткий."""
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
    
    # Захват целевого абзаца
    best_snippet = paragraphs[best_para_index].strip()
    
    # Если абзац слишком короткий (например, просто заголовок), захватываем следующий
    if len(best_snippet) < 200 and best_para_index + 1 < len(paragraphs):
        next_para = paragraphs[best_para_index + 1].strip()
        if next_para:
            best_snippet += "\n\n" + next_para
            
    if len(best_snippet) > 800:
        return best_snippet[:800] + "..."
    return best_snippet

def _score_and_extract(file_path: Path, content: str, keywords: list[str]) -> dict | None:
    """Вычисляет score файла и собирает объект результата."""
    content_lower = content.lower()
    score = 0
    filename_lower = file_path.stem.lower()
    first_200 = content_lower[:200]
    
    for kw in keywords:
        if kw in filename_lower:
            score += 5
        if kw in first_200:
            score += 2
    
    paragraphs = content.split('\n\n')
    for para in paragraphs:
        para_lower = para.lower()
        matches = sum(para_lower.count(kw) for kw in keywords)
        if matches > 0:
            score += matches 
            if re.match(r'^#{1,6}\s', para.strip()):
                for kw in keywords:
                    if kw in para_lower:
                        score += 3

    if score > 0:
        return {
            "file": file_path.name,
            "score": score,
            "tags": _parse_tags(content),
            "snippet": _extract_best_snippet(paragraphs, keywords)
        }
    return None

def execute_search(vault_dir: str | Path, query: str) -> dict[str, Any]:
    """Детерминированный RAG-движок: фильтрация стоп-слов, каскад AND -> OR, строгий JSON-ответ."""
    vault_path = Path(vault_dir)
    if not vault_path.exists() or not vault_path.is_dir():
        logger.error(f"Vault path not found: {vault_path}")
        return {"status": "error", "error_message": "Vault path does not exist", "results": []}

    # Очистка запроса от мусора и стоп-слов
    keywords = [word.lower() for word in query.split() if word.strip() and word.lower() not in STOP_WORDS]
    if not keywords:
        return {"status": "no_results", "message": "Query contains only stop-words or is empty", "results": []}

    all_md_files = list(vault_path.rglob("*.md"))
    
    def search_pass(mode: str) -> list[dict]:
        pass_results = []
        for file_path in all_md_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                content_lower = content.lower()
                
                if mode == "AND":
                    if not all(kw in content_lower for kw in keywords):
                        continue
                else: # OR
                    if not any(kw in content_lower for kw in keywords):
                        continue
                        
                res = _score_and_extract(file_path, content, keywords)
                if res:
                    pass_results.append(res)
            except Exception as e:
                logger.warning(f"Ошибка чтения {file_path.name}: {e}")
        return pass_results

    # Шаг 1: Строгий AND-поиск
    results = search_pass("AND")
    
    # Шаг 2: Fallback на OR-поиск, если AND выдал 0 и слов больше одного
    if not results and len(keywords) > 1:
        logger.info(f"AND search yielded 0 results for {keywords}. Falling back to OR.")
        results = search_pass("OR")

    if not results:
        return {"status": "no_results", "results": []}

    # Сортировка по score и срез
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"status": "ok", "results": results[:3]}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic Obsidian RAG Search")
    parser.add_argument("--query", required=True, help="Текст для поиска (атомарный запрос)")
    # ВНИМАНИЕ: Укажи путь к КОРНЮ базы, а не только к папке inbox
    parser.add_argument("--dir", default="/var/syncthing/vault", help="Путь к корню базы знаний")
    args = parser.parse_args()

    result = execute_search(args.dir, args.query)
    
    # Всегда выдаем JSON в stdout
    print(json.dumps(result, ensure_ascii=False, indent=2))
import re
from pathlib import Path
from typing import Any
from loguru import logger

def _parse_tags(content: str) -> list[str]:
    """Строгий парсинг тегов только из блока 'tags:' в YAML frontmatter."""
    tags = []
    yaml_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not yaml_match:
        return tags
    
    yaml_content = yaml_match.group(1)
    # Ищем блок tags: и захватываем все элементы списка под ним
    tags_match = re.search(r'^tags:\n((?:\s+- .*\n?)*)', yaml_content, re.MULTILINE)
    
    if tags_match:
        tag_lines = tags_match.group(1).split('\n')
        for line in tag_lines:
            line = line.strip()
            if line.startswith('-'):
                tags.append(line[1:].strip())
    return tags

def _extract_best_snippet(paragraphs: list[str], keywords: list[str]) -> str:
    """Умное извлечение сниппетов (уровень абзаца, приоритет заголовков h2/h3)."""
    candidates = []
    
    for para in paragraphs:
        para_lower = para.lower()
        matches = sum(para_lower.count(kw) for kw in keywords)
        
        if matches > 0:
            is_heading = bool(re.match(r'^#{2,3}\s', para.strip()))
            candidates.append((is_heading, matches, para.strip()))
            
    if not candidates:
        return "Сниппет не найден, но ключевые слова присутствуют."
        
    # Сортируем: сначала h2/h3 с совпадениями, затем по количеству совпадений
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_snippet = candidates[0][2]
    
    # Лимит на размер сниппета для экономии токенов
    if len(best_snippet) > 600:
        return best_snippet[:600] + "..."
    return best_snippet

def execute_search(vault_dir: str | Path, query: str) -> str | list[dict[str, Any]]:
    """
    Детерминированный RAG-движок со скорингом и хард-лимитами.
    Возвращает NO_RESULTS, если ничего не найдено.
    """
    vault_path = Path(vault_dir)
    if not vault_path.exists() or not vault_path.is_dir():
        logger.error(f"Vault path not found: {vault_path}")
        return "NO_RESULTS"

    # Атомарный запрос: убираем лишние пробелы, переводим в нижний регистр
    keywords = [word.lower() for word in query.split() if word.strip()]
    if not keywords:
        return "NO_RESULTS"

    all_md_files = list(vault_path.rglob("*.md"))
    results = []

    for file_path in all_md_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            content_lower = content.lower()
            
            # Фильтр: все слова из запроса должны быть в файле
            if not all(kw in content_lower for kw in keywords):
                continue
                
            score = 0
            filename_lower = file_path.stem.lower()
            first_200 = content_lower[:200]
            
            # +5 если keyword в заголовке файла
            for kw in keywords:
                if kw in filename_lower:
                    score += 5
                    
            # +2 если в первых 200 символах
            for kw in keywords:
                if kw in first_200:
                    score += 2
            
            paragraphs = content.split('\n\n')
            
            for para in paragraphs:
                para_lower = para.lower()
                matches = sum(para_lower.count(kw) for kw in keywords)
                if matches > 0:
                    # +1 за каждое совпадение
                    score += matches 
                    
                    # +3 если keyword в заголовке внутри файла
                    if re.match(r'^#{1,6}\s', para.strip()):
                        for kw in keywords:
                            if kw in para_lower:
                                score += 3

            if score > 0:
                results.append({
                    "file": file_path.name,
                    "score": score,
                    "tags": _parse_tags(content),
                    "snippet": _extract_best_snippet(paragraphs, keywords)
                })
                
        except Exception as e:
            logger.warning(f"Ошибка чтения {file_path.name}: {e}")

    if not results:
        return "NO_RESULTS"

    # Сортировка по score (убывание) и срез top_k = 3
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:3]
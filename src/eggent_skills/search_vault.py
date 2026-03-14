import re
import json
from pathlib import Path
from typing import List, Dict, Optional

def search_vault(
    search_path: str = '/app/vault',
    filename_pattern: str = r'.*\.md$',
    metadata_filters: Optional[Dict[str, str]] = None,
    fulltext_regex: Optional[str] = None,
    max_results: int = 10
) -> List[Dict]:
    results = []
    # Регулярка для захвата ТОЛЬКО YAML фронтматтера
    frontmatter_pattern = re.compile(r'^---\n(.*?)\n---', re.DOTALL)
    
    try:
        vault_path = Path(search_path)
        for md_file in vault_path.rglob('*.md'):
            # Фильтр по имени (включая игнор .stversions)
            if not re.match(filename_pattern, md_file.name):
                continue

            try:
                with md_file.open('r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue
            
            # Извлекаем фронтматтер
            fm_match = frontmatter_pattern.search(content)
            frontmatter_text = fm_match.group(1) if fm_match else ""

            # ФАЗА 1: Точный поиск по метаданным (YAML)
            if metadata_filters:
                match_all = True
                for key, pattern in metadata_filters.items():
                    # Ищем совпадение паттерна строго внутри блока фронтматтера
                    if not re.search(pattern, frontmatter_text, re.IGNORECASE):
                        match_all = False
                        break
                if not match_all:
                    continue

            # ФАЗА 2: Поиск по остальному тексту (если запрошен)
            fragments = []
            if fulltext_regex:
                # Читаем текст только после фронтматтера
                text_content = content[fm_match.end() if fm_match else 0:]
                text_matches = list(re.finditer(fulltext_regex, text_content, re.IGNORECASE))
                
                if not text_matches:
                    continue # Пропускаем файл, если текст не найден
                
                # Добавляем контекст (фрагменты текста) для LLM
                for m in text_matches[:2]:
                    start = max(0, m.start() - 40)
                    end = min(len(text_content), m.end() + 40)
                    fragments.append(text_content[start:end].replace('\n', ' ').strip())

            results.append({
                'path': str(md_file.relative_to(vault_path)),
                'fragments': fragments if fragments else None
            })

            if len(results) >= max_results:
                break

    except Exception as e:
        return [{'error': str(e)}]

    return results
#!/opt/eggent-python/bin/python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
import yaml

# --- CONSTANTS & WHITELISTS ---
IGNORED_DIRS: set[str] = {
    ".git", ".obsidian", ".stversions", "__pycache__", ".trash",
    ".syncthing", ".idea", ".vscode", "node_modules", ".venv", "venv"
}

BACKUP_SUFFIX_RE = re.compile(r"~\d{8}-\d{6}$")
TRANSIENT_RE = re.compile(r"(key|⚿|snapshot|test|final_test|temp)", re.IGNORECASE)

DOMAIN_WHITELIST = {"ai", "trading", "finance", "dev", "english", "obsidian", "automation"}
TYPE_WHITELIST = {"system", "note", "project", "article", "reference", "meeting", "person", "log", "inbox"}


def should_skip_path(path: Path) -> bool:
    """Проверка пути на игнорируемые директории."""
    return any(part in IGNORED_DIRS for part in path.parts)


def is_backup_file(filename: str) -> bool:
    """Проверка на файл бэкапа."""
    return bool(BACKUP_SUFFIX_RE.search(Path(filename).stem))


def is_transient_note(file_path: Path, title: str) -> bool:
    """Определяет временные, тестовые и чувствительные заметки."""
    if file_path.name.startswith("."):
        return True
    if TRANSIENT_RE.search(file_path.name):
        return True
    if title and TRANSIENT_RE.search(title):
        return True
    return False


def extract_frontmatter(content: str) -> tuple[str, str]:
    """Надежный line-based парсинг YAML frontmatter вместо регулярок."""
    lines = content.splitlines(keepends=True)
    if not lines or not lines[0].startswith("---"):
        return "", content

    yaml_lines = []
    body_lines = []
    in_yaml = True
    
    for i, line in enumerate(lines[1:], start=1):
        if in_yaml and line.startswith("---"):
            in_yaml = False
            body_lines = lines[i+1:]
            break
        elif in_yaml:
            yaml_lines.append(line)

    if in_yaml:  # Закрывающий --- не найден
        return "", content

    return "".join(yaml_lines), "".join(body_lines)


def get_canonical_title(frontmatter: dict, file_path: Path) -> str:
    """Извлекает канонический заголовок строго по ТЗ."""
    if isinstance(frontmatter, dict):
        aliases = frontmatter.get("aliases", [])
        if isinstance(aliases, list) and aliases:
            return str(aliases[0])
        if "title" in frontmatter and frontmatter["title"]:
            return str(frontmatter["title"])
    return file_path.stem


def classify_unprefixed_tag(tag: str, stats: dict) -> str:
    """Классифицирует тег и обновляет статистику конверсии."""
    if tag in TYPE_WHITELIST:
        stats["converted_to_type"] += 1
        return f"type/{tag}"
    if tag in DOMAIN_WHITELIST:
        stats["converted_to_domain"] += 1
        return f"domain/{tag}"
    stats["converted_to_entity"] += 1
    return f"entity/{tag}"


def normalize_tags(raw_tags: list, stats: dict) -> tuple[list[str], bool]:
    """Приводит теги к каноническому виду с учетом политик Phase 1."""
    if not raw_tags or not isinstance(raw_tags, list):
        return [], False

    seen = set()
    result = []
    changed = False

    for original_tag in raw_tags:
        if not isinstance(original_tag, str):
            continue

        # Сохраняем оригинальный регистр для дат, чистим пробелы
        clean_original = re.sub(r'\s*/\s*', '/', original_tag.strip())
        t_lower = clean_original.lower()
        if not t_lower:
            continue

        # 1. Special-case: Теги дат (гарантируем YYYY/Mon)
        if re.match(r'^\d{4}/[a-zа-я]+$', t_lower):
            parts = clean_original.split('/')
            normalized = f"{parts[0]}/{parts[1].capitalize()}"
            
        # 2. Уже нормализованные теги
        elif t_lower.startswith(("domain/", "entity/", "type/")):
            normalized = t_lower
            
        # 3. Вложенные теги (nested tags)
        elif "/" in t_lower:
            prefix = t_lower.split('/')[0]
            if prefix in DOMAIN_WHITELIST:
                normalized = f"domain/{t_lower}"
                stats["converted_to_domain"] += 1
            elif prefix in TYPE_WHITELIST:
                normalized = f"type/{t_lower}"
                stats["converted_to_type"] += 1
            else:
                # Оставляем как legacy/unresolved без авто-конверсии в entity
                normalized = t_lower 
                stats["legacy_nested_tags"] += 1
                
        # 4. Простые теги (без слеша)
        else:
            if t_lower in TYPE_WHITELIST:
                normalized = f"type/{t_lower}"
                stats["converted_to_type"] += 1
            elif t_lower in DOMAIN_WHITELIST:
                normalized = f"domain/{t_lower}"
                stats["converted_to_domain"] += 1
            else:
                normalized = f"entity/{t_lower}"
                stats["converted_to_entity"] += 1

        if normalized != original_tag:
            changed = True

        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    if len(result) != len([t for t in raw_tags if isinstance(t, str) and t.strip()]):
        changed = True

    return result, changed


def process_file(file_path: Path, args: argparse.Namespace, stats: dict) -> None:
    """Обрабатывает один Markdown файл с учетом политик Phase 1.2."""
    stats["scanned"] += 1
    
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать {file_path}: {e}")
        stats["failed"] += 1
        return

    yaml_str, body = extract_frontmatter(content)
    
    frontmatter = {}
    if yaml_str:
        try:
            frontmatter = yaml.safe_load(yaml_str) or {}
        except yaml.YAMLError:
            print(f"[WARN] Невалидный YAML в {file_path.name}")
            stats["invalid_yaml"] += 1
            return

    canonical_title = get_canonical_title(frontmatter, file_path)

    # 1. Проверка на Transient Notes
    if is_transient_note(file_path, canonical_title):
        stats["excluded_transient"] += 1
        return

    raw_tags = frontmatter.get("tags", [])
    needs_update = False

    # 2. Обработка заметок БЕЗ тегов
    if not raw_tags:
        if args.untagged_policy == "skip":
            stats["skipped_no_tags"] += 1
            return
            
        elif args.untagged_policy == "scaffold":
            if "00 System" in file_path.parts:
                frontmatter["canonical_title"] = canonical_title
                frontmatter.setdefault("note_granularity", "atomic")
                frontmatter["tags"] = []
                frontmatter["entity_refs"] = []
                frontmatter["domain_refs"] = []
                frontmatter["type_refs"] = []
                frontmatter["relation_refs"] = []
                
                stats["scaffolded_no_tags"] += 1
                needs_update = True
            else:
                stats["skipped_no_tags"] += 1
                return
                
        elif args.untagged_policy == "classify":
            stats["skipped_no_tags"] += 1
            return

    # 3. Обработка заметок С тегами (Normal Migration)
    else:
        new_tags, tags_changed = normalize_tags(raw_tags, stats)
        if tags_changed:
            frontmatter["tags"] = new_tags
            needs_update = True
            
        for ref_field in ["entity_refs", "domain_refs", "type_refs", "relation_refs"]:
            if ref_field not in frontmatter:
                frontmatter[ref_field] = []
                needs_update = True
                
        if "canonical_title" not in frontmatter:
            frontmatter["canonical_title"] = canonical_title
            needs_update = True

    if not needs_update:
        stats["untouched"] += 1
        return

    print(f"\n[{'APPLY' if args.apply else 'DRY-RUN'}] {file_path.name}")
    if raw_tags:
        print(f"  Old Tags: {raw_tags}")
        print(f"  New Tags: {frontmatter.get('tags', [])}")
    else:
        print(f"  Action: Scaffold applied (Policy: {args.untagged_policy})")

    if args.apply:
        new_yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
        new_content = f"---\n{new_yaml_str}---\n{body}"
        
        try:
            file_path.write_text(new_content, encoding="utf-8")
            stats["changed"] += 1  # Увеличиваем ТОЛЬКО после успешной записи
        except Exception as e:
            print(f"[ERROR] Ошибка записи в {file_path.name}: {e}")
            stats["failed"] += 1
    else:
        stats["changed"] += 1  # Для dry-run считаем виртуальное изменение


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1.2: Controlled Corpus Migration")
    parser.add_argument("--dir", default="/app/vault", help="Путь к корню базы знаний")
    parser.add_argument("--apply", action="store_true", help="Выполнить физическую перезапись файлов")
    parser.add_argument("--dry-run", action="store_true", help="Показать планируемые изменения без записи")
    parser.add_argument("--untagged-policy", choices=["skip", "scaffold", "classify"], default="skip", 
                        help="Политика для заметок без тегов (по умолчанию: skip)")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        print("Ошибка: Необходимо указать --dry-run или --apply")
        sys.exit(1)
        
    if args.apply and args.dry_run:
        print("Ошибка: Нельзя использовать --apply и --dry-run одновременно")
        sys.exit(1)

    vault_path = Path(args.dir)
    if not vault_path.exists() or not vault_path.is_dir():
        print(f"Ошибка: Директория {vault_path} не найдена.", file=sys.stderr)
        sys.exit(1)

    stats = {
        "scanned": 0,
        "changed": 0,
        "failed": 0,
        "invalid_yaml": 0,
        "untouched": 0,
        "skipped_no_tags": 0,
        "scaffolded_no_tags": 0,
        "excluded_transient": 0,
        "converted_to_entity": 0,
        "converted_to_domain": 0,
        "converted_to_type": 0,
        "legacy_nested_tags": 0
    }

    print(f"Запуск Phase 1.2 Migration: {vault_path}")
    print(f"Режим: {'APPLY (Запись)' if args.apply else 'DRY-RUN (Только чтение)'}")
    print(f"Untagged Policy: {args.untagged_policy}\n")

    md_files = [
        p for p in vault_path.rglob("*.md")
        if not should_skip_path(p) and not is_backup_file(p.name)
    ]

    for file_path in md_files:
        process_file(file_path, args, stats)

    print("\n" + "="*45)
    print("MIGRATION REPORT")
    print("="*45)
    print(f"Scanned files:          {stats['scanned']}")
    print(f"Changed files:          {stats['changed']}")
    print(f"Failed (errors):        {stats['failed']}")
    print(f"Untouched by rule:      {stats['untouched']}")
    print(f"Invalid YAML files:     {stats['invalid_yaml']}")
    print("-" * 45)
    print(f"Excluded Transient:     {stats['excluded_transient']}")
    print(f"Skipped (No Tags):      {stats['skipped_no_tags']}")
    print(f"Scaffolded (No Tags):   {stats['scaffolded_no_tags']}")
    print("-" * 45)
    print(f"Converted to entity/*:  {stats['converted_to_entity']}")
    print(f"Converted to domain/*:  {stats['converted_to_domain']}")
    print(f"Converted to type/*:    {stats['converted_to_type']}")
    print(f"Legacy nested tags:     {stats['legacy_nested_tags']}")
    print("="*45)


if __name__ == "__main__":
    main()
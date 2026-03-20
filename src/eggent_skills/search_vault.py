#!/opt/eggent-python/bin/python3
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


STOP_WORDS: set[str] = {
    "и", "или", "но", "а", "в", "во", "на", "по", "с", "со", "к", "ко", "у", "о", "об",
    "от", "до", "за", "из", "для", "под", "над", "при", "не", "ни", "же", "ли", "бы",
    "это", "этот", "эта", "эти", "тот", "та", "те", "как", "что", "где", "когда", "почему",
    "зачем", "какой", "какая", "какие", "which", "what", "how", "why", "where", "when",
    "the", "a", "an", "to", "of", "in", "on", "for", "with", "by", "is", "are", "was",
    "were", "be", "been", "being", "and", "or", "not", "from", "into", "about", "my",
    "your", "our", "their", "его", "ее", "их", "мой", "моя", "мои", "наш", "наша", "наши",
    "сделай", "найди", "покажи", "расскажи", "нужен", "нужно", "надо", "please",
}

SYNTHETIC_RE = re.compile(r"(synthetic|test|injection|aggregated|summary|trap)", re.IGNORECASE)
ARCHIVE_RE = re.compile(r"(/archives?/|old|legacy|v\d+\.\d+)", re.IGNORECASE)
CORE_DOC_RE = re.compile(r"(core|protocol|architecture|index|standard)", re.IGNORECASE)
RELATION_TAGS = {"type/contact", "type/person", "type/dependency", "type/ownership"}

NON_ENTITY_TERMS: set[str] = {
    "запрещено", "запрет", "правило", "правила", "чеклист", "аудит", "безопасность",
    "безопасности", "поиск", "поиска", "настройка", "настройки", "инструкция",
    "инструкции", "система", "системы", "проект", "проекта", "сервер", "инфраструктура",
    "проксирование", "hardening", "security", "checklist", "setup", "guide", "protocol",
    "retrieval", "search", "vault", "dev", "core", "system", "note", "project",
}

SYSTEM_TYPE_TAGS: set[str] = {
    "type/system",
    "system",
}

IGNORED_DIRS: set[str] = {
    ".git",
    ".obsidian",
    ".stversions",
    "__pycache__",
    ".trash",
    ".syncthing",
    ".idea",
    ".vscode",
    "node_modules",
    ".venv",
    "venv",
}

BACKUP_SUFFIX_RE = re.compile(r"~\d{8}-\d{6}$")
YAML_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
TAGS_BLOCK_RE = re.compile(r"^tags:\s*\n((?:\s*-\s*.*\n?)*)", re.MULTILINE)
H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
PROMPTISH_RE = re.compile(
    r"(prompt|instruction|system core|protocol|dev protocol|guideline|rules?|policy|policies)",
    re.IGNORECASE,
)


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.strip().lower()
    value = value.replace("ё", "е")
    value = re.sub(r"[\"'`“”‘’]", "", value)
    value = re.sub(r"[_/]+", " ", value)
    value = re.sub(r"[^0-9a-zа-яіїєґ+\-.\s]", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _slugify(value: str) -> str:
    value = _normalize_text(value)
    value = value.replace(" ", "-")
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def should_skip_path(path: Path) -> bool:
    parts = set(path.parts)
    return any(part in IGNORED_DIRS for part in parts)


def is_backup_file(filename: str) -> bool:
    stem = Path(filename).stem
    return bool(BACKUP_SUFFIX_RE.search(stem))


def _canonical_title(title: str) -> str:
    cleaned = BACKUP_SUFFIX_RE.sub("", title)
    return _normalize_text(cleaned)


def _parse_tags(content: str) -> list[str]:
    """Строгий парсинг тегов только из YAML frontmatter."""
    tags: list[str] = []
    yaml_match = YAML_FRONTMATTER_RE.match(content)
    if not yaml_match:
        return tags

    yaml_content = yaml_match.group(1)
    tags_match = TAGS_BLOCK_RE.search(yaml_content)
    if not tags_match:
        return tags

    for raw_line in tags_match.group(1).splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        tag = line[1:].strip().strip('"').strip("'")
        if tag:
            tags.append(tag)
    return tags


def _normalize_tag(tag: str) -> str:
    tag = tag.strip().strip('"').strip("'")
    if not tag:
        return ""
    if "/" in tag:
        prefix, rest = tag.split("/", 1)
        return f"{_normalize_text(prefix)}/{_slugify(rest)}"
    return _slugify(tag)


def _extract_h1(content: str) -> str:
    match = H1_RE.search(content)
    return match.group(1).strip() if match else ""


def _split_paragraphs(content: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]


def _extract_best_snippet(paragraphs: list[str], keywords: list[str]) -> str:
    if not paragraphs:
        return "Сниппет не найден."

    candidates: list[tuple[int, int, int, str, int]] = []
    for idx, para in enumerate(paragraphs):
        para_norm = _normalize_text(para)
        if not para_norm:
            continue
        kw_hits = sum(para_norm.count(kw) for kw in keywords)
        if kw_hits <= 0:
            continue
        is_heading = 1 if HEADING_RE.match(para.strip()) else 0
        proximity_bonus = 1 if idx < 8 else 0
        candidates.append((is_heading, kw_hits, proximity_bonus, para.strip(), idx))

    if not candidates:
        return "Сниппет не найден, но ключевые слова присутствуют."

    candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    _, _, _, best_para, best_idx = candidates[0]

    snippet = best_para
    if len(snippet) < 220 and best_idx + 1 < len(paragraphs):
        next_para = paragraphs[best_idx + 1].strip()
        if next_para and not next_para.startswith("---"):
            snippet += "\n\n" + next_para

    return snippet[:800] + "..." if len(snippet) > 800 else snippet


def _extract_query_keywords(query: str) -> list[str]:
    query_norm = _normalize_text(query)
    if not query_norm:
        return []

    raw_tokens = re.findall(r"[0-9a-zа-яіїєґ+\-.]{2,}", query_norm, flags=re.IGNORECASE)
    keywords: list[str] = []
    seen: set[str] = set()

    for token in raw_tokens:
        token = token.strip(".-+")
        if len(token) < 2:
            continue
        if token in STOP_WORDS:
            continue
        if token not in seen:
            keywords.append(token)
            seen.add(token)

    return keywords


def _build_entity_registry(vault_path: Path) -> dict[str, set[str]]:
    """
    Собирает только реальные entity-теги из базы.
    Возвращает:
      canonical_entity -> aliases
    Пример:
      "entity/eggent" -> {"eggent", "eggent-ai-agent", "eggent ai agent"}
    """
    registry: dict[str, set[str]] = {}

    for file_path in vault_path.rglob("*.md"):
        if should_skip_path(file_path) or is_backup_file(file_path.name):
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            raw_tags = _parse_tags(content)
            h1 = _extract_h1(content)
            stem = file_path.stem
        except Exception:
            continue

        for raw_tag in raw_tags:
            tag = _normalize_tag(raw_tag)
            if not tag.startswith("entity/"):
                continue

            entity_key = tag
            aliases = registry.setdefault(entity_key, set())

            name = entity_key.split("/", 1)[1]
            aliases.add(name)
            aliases.add(name.replace("-", " "))

            stem_norm = _normalize_text(BACKUP_SUFFIX_RE.sub("", stem))
            if stem_norm:
                aliases.add(stem_norm)
                aliases.add(_slugify(stem_norm))

            h1_norm = _normalize_text(h1)
            if h1_norm:
                aliases.add(h1_norm)
                aliases.add(_slugify(h1_norm))

    return registry


def _extract_validated_entities(
    keywords: list[str],
    query: str,
    entity_registry: dict[str, set[str]],
) -> list[str]:
    """
    Не превращает все keywords в entity/*.
    Возвращает только те entity, которые реально существуют в базе
    и совпали по alias/canonical form.
    """
    query_norm = _normalize_text(query)
    keyword_set = set(keywords)
    validated: list[str] = []

    for entity_key, aliases in entity_registry.items():
        canonical_name = entity_key.split("/", 1)[1]
        canonical_parts = set(canonical_name.split("-"))

        matched = False

        if canonical_name in keyword_set:
            matched = True
        elif canonical_name.replace("-", " ") in query_norm:
            matched = True
        elif canonical_parts and canonical_parts.issubset(keyword_set):
            matched = True
        else:
            for alias in aliases:
                alias_norm = _normalize_text(alias)
                if not alias_norm:
                    continue
                alias_slug = _slugify(alias_norm)
                alias_parts = set(alias_slug.split("-")) if alias_slug else set()

                if alias_slug and alias_slug in keyword_set:
                    matched = True
                    break
                if alias_norm and alias_norm in query_norm:
                    matched = True
                    break
                if alias_parts and alias_parts.issubset(keyword_set):
                    matched = True
                    break

        if matched:
            validated.append(entity_key)

    validated.sort()
    return validated


def _filename_aliases(file_path: Path) -> set[str]:
    stem = BACKUP_SUFFIX_RE.sub("", file_path.stem)
    stem_norm = _normalize_text(stem)
    if not stem_norm:
        return set()
    return {
        stem_norm,
        _slugify(stem_norm),
        stem_norm.replace("-", " "),
    }


def _compute_base_score(
    filename_norm: str,
    headings_norm: list[str],
    first_200_norm: str,
    paragraphs_norm: list[str],
    keywords: list[str],
) -> int:
    score = 0

    for kw in keywords:
        if kw in filename_norm:
            score += 5
        if kw in first_200_norm:
            score += 2

    for heading in headings_norm:
        heading_hits = sum(heading.count(kw) for kw in keywords)
        if heading_hits > 0:
            score += heading_hits + 3

    for para in paragraphs_norm:
        para_hits = sum(para.count(kw) for kw in keywords)
        if para_hits > 0:
            score += min(para_hits, 3)

    return score


def _compute_entity_score(
    validated_entities: list[str],
    norm_tags: list[str],
    filename_aliases: set[str],
    h1_norm: str,
    headings_norm: list[str],
) -> tuple[int, list[str], bool]:
    entity_score = 0
    entity_matches: list[str] = []
    direct_target = False

    tag_set = set(norm_tags)

    for entity_key in validated_entities:
        matched = False
        entity_name = entity_key.split("/", 1)[1]
        entity_phrase = entity_name.replace("-", " ")

        if entity_key in tag_set:
            entity_score += 8
            matched = True
            direct_target = True

        if entity_phrase and h1_norm and entity_phrase in h1_norm:
            entity_score += 5
            matched = True

        if entity_name in filename_aliases or entity_phrase in filename_aliases:
            entity_score += 4
            matched = True

        for heading in headings_norm:
            if entity_phrase and entity_phrase in heading:
                entity_score += 3
                matched = True
                break

        if matched:
            entity_matches.append(entity_key)

    return entity_score, sorted(set(entity_matches)), direct_target


def _looks_like_prompt_or_meta(filename_norm: str, headings_norm: list[str]) -> bool:
    joined = " | ".join([filename_norm, *headings_norm[:5]])
    return bool(PROMPTISH_RE.search(joined))


def _score_and_extract(
    file_path: Path,
    content: str,
    keywords: list[str],
    validated_entities: list[str],
    query: str,
) -> dict[str, Any] | None:
    content_norm = _normalize_text(content)
    if not content_norm:
        return None

    raw_tags = _parse_tags(content)
    norm_tags = [_normalize_tag(t) for t in raw_tags if _normalize_tag(t)]
    h1 = _extract_h1(content)
    h1_norm = _normalize_text(h1)
    filename_norm = _normalize_text(BACKUP_SUFFIX_RE.sub("", file_path.stem))

    base_score = _compute_base_score(
        filename_norm=filename_norm,
        headings_norm=[],
        first_200_norm=_normalize_text(content[:200]),
        paragraphs_norm=[],
        keywords=keywords,
    )

    entity_score, entity_matches, direct_target = _compute_entity_score(
        validated_entities=validated_entities,
        norm_tags=norm_tags,
        filename_aliases={filename_norm},
        h1_norm=h1_norm,
        headings_norm=[],
    )

    canonical_boost = 0
    query_norm = _normalize_text(query)

    if query_norm == filename_norm or (h1_norm and query_norm == h1_norm):
        canonical_boost += 40
    elif query_norm in filename_norm:
        canonical_boost += 20

    if any(tag in {"type/system", "type/protocol", "system", "protocol"} for tag in norm_tags):
        canonical_boost += 15

    if filename_norm.startswith("00 "):
        canonical_boost += 10

    path_str = str(file_path).lower()
    is_archive = bool(ARCHIVE_RE.search(filename_norm)) or "/archives/" in path_str
    penalty = 0
    if is_archive:
        penalty -= 30

    total_score = base_score + entity_score + canonical_boost + penalty

    if total_score <= 0 and not direct_target:
        return None

    return {
        "title": file_path.stem,
        "file": file_path.name,
        "path": str(file_path),
        "score": total_score,
        "canonical_boost": canonical_boost,
        "entity_score": entity_score,
        "tags": raw_tags,
        "snippet": content[:300] + "...",
    }


def execute_search(vault_dir: str | Path, query: str, subdir: str = "") -> dict[str, Any]:
    base_path = Path(vault_dir).resolve()

    if not base_path.exists() or not base_path.is_dir():
        print(f"Vault path not found: {base_path}", file=sys.stderr)
        return {
            "status": "error",
            "error_message": "Vault path does not exist",
            "results": [],
        }

    search_path = (base_path / subdir).resolve()

    if not search_path.exists():
        return {
            "status": "error",
            "error_message": f"Path not found: {subdir}",
            "results": [],
        }

    if not search_path.is_relative_to(base_path):
        return {
            "status": "error",
            "error_message": "Security Alert: Search directory is outside the allowed vault root",
            "results": [],
        }

    if not search_path.is_dir():
        return {
            "status": "error",
            "error_message": f"Search path is not a directory: {subdir}",
            "results": [],
        }

    keywords = _extract_query_keywords(query)
    if not keywords:
        return {
            "status": "no_results",
            "message": "Query contains only stop-words or is empty",
            "results": [],
        }

    entity_registry = _build_entity_registry(base_path)
    validated_entities = _extract_validated_entities(keywords, query, entity_registry)

    valid_md_files = [
        p for p in search_path.rglob("*.md")
        if not should_skip_path(p) and not is_backup_file(p.name)
    ]

    def search_pass(mode: str) -> list[dict[str, Any]]:
        pass_results: list[dict[str, Any]] = []

        for file_path in valid_md_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                content_norm = _normalize_text(content)

                if mode == "AND":
                    if not all(kw in content_norm for kw in keywords):
                        continue
                else:
                    content_hit = any(kw in content_norm for kw in keywords)
                    entity_hit = False

                    if validated_entities:
                        filename_norm = _normalize_text(BACKUP_SUFFIX_RE.sub("", file_path.stem))
                        h1_norm = _normalize_text(_extract_h1(content))
                        raw_tags = [_normalize_tag(t) for t in _parse_tags(content)]

                        for entity_key in validated_entities:
                            entity_name = entity_key.split("/", 1)[1]
                            entity_phrase = entity_name.replace("-", " ")
                            if (
                                entity_key in raw_tags
                                or entity_name in filename_norm
                                or entity_phrase in filename_norm
                                or (h1_norm and entity_phrase in h1_norm)
                            ):
                                entity_hit = True
                                break

                    if not content_hit and not entity_hit:
                        continue

                res = _score_and_extract(
                    file_path=file_path,
                    content=content,
                    keywords=keywords,
                    validated_entities=validated_entities,
                    query=query,
                )
                if res:
                    pass_results.append(res)
            except Exception:
                continue

        return pass_results

    results = search_pass("AND")
    if not results and len(keywords) > 1:
        results = search_pass("OR")

    if not results:
        return {
            "status": "no_results",
            "results": [],
        }

    results.sort(key=lambda x: (-x["entity_score"], -x["score"], x["file"], x["path"]))

    unique_results: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for res in results:
        canonical = _canonical_title(res["title"])
        if canonical in seen_titles:
            continue
        seen_titles.add(canonical)
        unique_results.append(res)

    unique_results.sort(
        key=lambda x: (
            -x["entity_score"],
            -x["score"],
            x["file"].lower(),
            x["path"].lower(),
        )
    )

    return {
        "status": "ok",
        "results": unique_results[:3],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic Obsidian RAG Search")
    parser.add_argument("--query", required=True, help="Текст для поиска")
    parser.add_argument(
        "--dir",
        default="/app/vault",
        help="Путь к корню базы знаний внутри контейнера",
    )
    parser.add_argument(
        "--subdir",
        default="",
        help="Ограничить поиск папкой (например, '00 System')",
    )
    args = parser.parse_args()

    result = execute_search(args.dir, args.query, args.subdir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
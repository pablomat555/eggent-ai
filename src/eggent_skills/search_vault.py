import re
from pathlib import Path
from typing import Any
from loguru import logger

def _extract_snippet(content: str, keywords: list[str], context_window: int = 100) -> str:
    """Extracts a context snippet around the first found keyword."""
    content_clean = re.sub(r'\s+', ' ', content)
    content_lower = content_clean.lower()
    
    for word in keywords:
        idx = content_lower.find(word)
        if idx != -1:
            start = max(0, idx - context_window)
            end = min(len(content_clean), idx + len(word) + context_window)
            return f"...{content_clean[start:end].strip()}..."
    return "No exact snippet matched."

def _parse_tags(content: str) -> list[str]:
    """Extracts tags from Obsidian YAML frontmatter."""
    tags = []
    if content.startswith("---"):
        yaml_block = content.split("---", 2)
        if len(yaml_block) >= 3:
            # Match tags array or inline tags
            tag_matches = re.findall(r'-\s*([^\n]+)', yaml_block[1])
            tags = [t.strip() for t in tag_matches if t.strip()]
    return tags

def execute_search(vault_dir: str | Path, query: str, tags: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Searches the Obsidian vault. Features AND logic, case-insensitive matching, 
    snippet extraction, and graceful fallback if tag filtering yields 0 results.
    """
    vault_path = Path(vault_dir)
    if not vault_path.exists() or not vault_path.is_dir():
        logger.error(f"Vault path not found: {vault_path}")
        return [{"error": "Vault path does not exist."}]

    try:
        keywords = [word.lower() for word in query.split() if word.strip()]
        all_md_files = list(vault_path.rglob("*.md"))
        
        def _search_pass(filter_tags: list[str] | None) -> list[dict[str, Any]]:
            results = []
            for file_path in all_md_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    content_lower = content.lower()
                    
                    # 1. Check Keywords (AND logic)
                    if not all(kw in content_lower for kw in keywords):
                        continue
                        
                    # 2. Check Tags (if provided)
                    if filter_tags:
                        file_tags = _parse_tags(content)
                        if not any(t in file_tags for t in filter_tags):
                            continue
                            
                    # 3. Assemble Result
                    results.append({
                        "file": file_path.name,
                        "path": str(file_path),
                        "snippet": _extract_snippet(content, keywords),
                        "tags": _parse_tags(content)
                    })
                except Exception as e:
                    logger.warning(f"Could not read {file_path.name}: {e}")
            return results

        # First Pass: Strict search with tags
        matched_results = _search_pass(tags)
        
        # Failsafe: If 0 results and tags were used, drop tags and retry
        if not matched_results and tags:
            logger.info("0 results with tags. Dropping tag filter for broader search.")
            matched_results = _search_pass(None)

        return matched_results[:10]  # Limit payload size

    except Exception as e:
        logger.exception("Search execution failed.")
        return [{"error": str(e)}]
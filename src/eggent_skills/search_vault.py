import os
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
    """
    Optimized search for Obsidian vault with two-phase approach:
    1. Pre-filter by filename and YAML metadata
    2. Optional full-text search using regex
    """
    results = []
    metadata_pattern = re.compile(r'^---\n(.*?)\n---', re.DOTALL)
    
    try:
        vault_path = Path(search_path)
        for md_file in vault_path.rglob('*.md'):
            if not re.match(filename_pattern, md_file.name):
                continue

            # Phase 1: Metadata parsing
            with md_file.open('r', encoding='utf-8') as f:
                content = f.read()
            
            metadata_match = metadata_pattern.search(content)
            file_meta = {}
            if metadata_match:
                try:
                    meta_lines = metadata_match.group(1).split('\n')
                    file_meta = {
                        line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip()
                        for line in meta_lines if ':' in line
                    }
                except Exception as e:
                    continue

            # Apply metadata filters
            if metadata_filters:
                match = all(
                    re.search(pattern, file_meta.get(key, ''), re.IGNORECASE)
                    for key, pattern in metadata_filters.items()
                )
                if not match:
                    continue

            # Phase 2: Full-text search
            fragments = []
            if fulltext_regex:
                try:
                    text_content = content[metadata_match.end() if metadata_match else 0:]
                    text_matches = re.finditer(fulltext_regex, text_content, re.DOTALL)
                    fragments = [{
                        'text': m.group(0),
                        'start_line': text_content.count('\n', 0, m.start()) + 1,
                        'end_line': text_content.count('\n', 0, m.end()) + 1
                    } for m in text_matches]
                except re.error:
                    return [{'error': 'Invalid regex pattern'}]

            results.append({
                'path': str(md_file.relative_to(vault_path)),
                'metadata': file_meta,
                'fragments': fragments,
                'fulltext_searched': fulltext_regex is not None
            })

            if len(results) >= max_results:
                break

    except Exception as e:
        return [{'error': f'Search failed: {str(e)}'}]

    return results[:max_results]

# JSON Schema for MCP registration
MCP_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Vault Search Tool",
    "description": "Optimized search for Obsidian vault with metadata filtering and regex fulltext search",
    "type": "object",
    "properties": {
        "search_path": {
            "type": "string",
            "default": "/app/vault",
            "description": "Root path for searching"
        },
        "filename_pattern": {
            "type": "string",
            "default": ".*\\.md$",
            "description": "Regex pattern for filename matching"
        },
        "metadata_filters": {
            "type": "object",
            "additionalProperties": {
                "type": "string",
                "description": "Regex pattern for metadata value matching"
            },
            "description": "Key-value pairs for metadata filtering"
        },
        "fulltext_regex": {
            "type": "string",
            "description": "Regex pattern for fulltext search"
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 10
        }
    },
    "required": [],
    "additionalProperties": False
}
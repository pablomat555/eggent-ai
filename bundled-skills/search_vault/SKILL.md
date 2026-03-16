---
name: search_vault
description: Безопасный прожектор-поиск по Obsidian Vault. Читает только YAML-фронтматтер + захватывает ±1000 символов контекста. Поддерживает фильтры domain, project, tags.
allowed-tools: Bash(python3 /app/bundled-skills/search_vault/search_vault.py)
---

# search_vault

**Назначение**  
Инструмент для Second Brain Agent. Ищет заметки по тегам, project, domain и тексту без галлюцинаций.

**Параметры**  
- `text` — строка для поиска  
- `metadata` — объект `{ "domain": "dev", "project": "Second Brain", "tags": ["system"] }`

**Как используется**  
Автоматически вызывается Библиотекарем при запросах "найди заметки domain: dev".
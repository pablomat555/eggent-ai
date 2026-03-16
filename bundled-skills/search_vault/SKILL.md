# search_vault

**Описание:**  
Безопасный прожектор-поиск по Obsidian Vault. Читает только YAML-фронтматтер + захватывает ±1000 символов контекста вокруг совпадения.

**Command:**  
`python3 /app/bundled-skills/search_vault/search_vault.py`

**Параметры (JSON):**  
- `text` (string) — полнотекстовый поиск  
- `metadata` (object) — фильтры: `{ "domain": "dev", "project": "Second Brain", "tags": ["system"] }`

**Как использовать:**  
Автоматически вызывается Библиотекарем при запросах "найди заметки domain: dev" или "поиск по тегу #intelligence-os".
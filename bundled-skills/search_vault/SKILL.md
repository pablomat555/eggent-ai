# search_vault

**Описание:** Безопасный поиск по Obsidian Vault (поиск по YAML-метаданным + полнотекстовый прожектор).

**Command:**  
`python3 /app/bundled-skills/search_vault/search_vault.py`

**Schema:**  
- `text` — строка для поиска  
- `metadata` — объект { "domain": "...", "project": "...", "tags": ["..."] }

**Использование в промпте:**  
Вызывается автоматически Библиотекарем при запросах типа "найди заметки domain: dev".
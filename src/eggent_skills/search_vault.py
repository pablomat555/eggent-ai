import os
import re
import json
import argparse
import sys

# Важно: укажи здесь правильный путь к твоему Vault внутри контейнера!
# Согласно архитектуре, это либо /var/syncthing/oo-system, либо /app/core
VAULT_DIR = "/app/vault"

def search_vault(search_text, search_tags):
    if not os.path.exists(VAULT_DIR):
        print(f"Ошибка: Директория Vault '{VAULT_DIR}' не найдена внутри контейнера. Проверьте Volumes в docker-compose.")
        sys.exit(1)

    results = []
    yaml_pattern = re.compile(r'^---\n(.*?)\n---', re.DOTALL)

    for root, dirs, files in os.walk(VAULT_DIR):
        # Жесткая блокировка скрытых папок (.stversions, .git, .obsidian)
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file in files:
            if not file.endswith('.md'):
                continue

            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                match = yaml_pattern.search(content)
                yaml_text = match.group(1) if match else ""

                hit = False
                # Ищем по тексту
                if search_text and search_text.lower() in content.lower():
                    hit = True
                
                # Ищем по тегам (во фронтматтере и в тексте)
                if search_tags:
                    for tag in search_tags:
                        clean_tag = tag.replace("#", "").lower()
                        if clean_tag in yaml_text.lower() or f"#{clean_tag}" in content.lower():
                            hit = True

                if hit:
                    # Отдаем агенту имя файла и небольшой кусок контекста
                    snippet = content[:200].replace('\n', ' ') + "..."
                    results.append(f"Файл: {file} | Контекст: {snippet}")
                    
                    # Защита от переполнения контекста ИИ (лимит 10 заметок)
                    if len(results) >= 10:
                        return results

            except Exception:
                continue # Игнорируем битые файлы

    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="")
    parser.add_argument("--metadata", default="{}")
    args = parser.parse_args()

    try:
        meta = json.loads(args.metadata)
        tags = meta.get("tags", [])
    except:
        tags = []

    found = search_vault(args.text, tags)
    
    if found:
        print("✅ НАЙДЕНЫ ЗАМЕТКИ:")
        for f in found:
            print(f"- {f}")
    else:
        print("❌ Заметки не найдены. База пуста по этому запросу.")
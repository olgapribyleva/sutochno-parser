"""
ПОИСК КОНКУРЕНТОВ (тест) — собирает ID объявлений со страницы результатов Суточно.

Ольга задаёт фильтры на Суточно (район, комнаты, гости), копирует ссылку
страницы результатов и передаёт её в workflow (поле search_url). Робот
открывает ссылку, прокручивает и выводит найденные ID компактным блоком
<<<SEARCH ... SEARCH>>> — его легко скопировать из лога GitHub Actions.

Запуск: workflow «Поиск конкурентов (тест)» (search-test.yml) с заполненной
ссылкой, или локально:  SEARCH_URL="https://sutochno.ru/..." python competitors_search.py
"""

import os
import json

from main import search_listings

SEARCH_URL = os.environ.get("SEARCH_URL", "").strip()

# Сколько раз прокрутить страницу (больше — больше карточек подгрузится).
SCROLLS = 16


def main():
    if not SEARCH_URL:
        print("НЕТ ССЫЛКИ: задай SEARCH_URL (в workflow — поле search_url).")
        return

    print("Открываю страницу результатов:", SEARCH_URL)
    res = search_listings(SEARCH_URL, scrolls=SCROLLS)

    items = res.get("items", [])
    compact = [{"id": x["id"], "text": x.get("text", "")[:160]} for x in items]

    print("РЕЗУЛЬТАТ (копируй весь блок ниже):")
    print("<<<SEARCH")
    print(json.dumps({
        "ok": res.get("ok"),
        "count": res.get("count"),
        "error": (res.get("error", "") or "")[:200],
        "ids": [x["id"] for x in items],
        "items": compact[:120],
    }, ensure_ascii=False, indent=2))
    print("SEARCH>>>")

    # Диагностика (если нашлось 0 — по ней пойму, что на странице)
    print("<<<DIAG")
    print(json.dumps(res.get("diag", {}), ensure_ascii=False, indent=2))
    print("DIAG>>>")


if __name__ == "__main__":
    main()

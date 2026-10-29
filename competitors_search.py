"""
ПОИСК КОНКУРЕНТОВ — собирает объявления со страницы результатов Суточно
через скрытый API (searchObjectsOnMap): ID, цена, координаты.

Ольга задаёт фильтры на Суточно, копирует ссылку результатов и передаёт её
в workflow (поле search_url). Робот открывает ссылку, ловит ответ API и
выводит компактный блок <<<SEARCH ... SEARCH>>> со списком ID и цен —
его легко скопировать из лога GitHub Actions.

Запуск: workflow «Поиск конкурентов (тест)» (search-test.yml) с заполненной
ссылкой, или локально:  SEARCH_URL="https://sutochno.ru/..." python competitors_search.py
"""

import os
import json

from main import search_listings

SEARCH_URL = os.environ.get("SEARCH_URL", "").strip()


def main():
    if not SEARCH_URL:
        print("НЕТ ССЫЛКИ: задай SEARCH_URL (в workflow — поле search_url).")
        return

    print("Открываю страницу результатов:", SEARCH_URL)
    res = search_listings(SEARCH_URL)

    items = res.get("items", [])
    # компактно: id + цена (цена со скидкой, если есть)
    rows = []
    for x in items:
        price = x.get("salePrice") or x.get("price")
        rows.append({"id": x["id"], "price": price})

    print("РЕЗУЛЬТАТ (копируй весь блок ниже):")
    print("<<<SEARCH")
    print(json.dumps({
        "ok": res.get("ok"),
        "count": res.get("count"),
        "error": (res.get("error", "") or "")[:200],
        "ids": [x["id"] for x in items],
        "rows": rows,
    }, ensure_ascii=False, indent=2))
    print("SEARCH>>>")


if __name__ == "__main__":
    main()

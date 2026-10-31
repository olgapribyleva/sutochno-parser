"""
ОБОГАЩЕНИЕ СПИСКА КОНКУРЕНТОВ (Пологая 62) — открывает страницу каждого
объявления Суточно и вытаскивает: название, комнаты, гостей, площадь,
рейтинг, число отзывов, цену. Печатает компактный блок <<<ENRICH ... ENRICH>>>
который легко скопировать из лога GitHub Actions и передать Клодику.

Запуск: workflow «Обогащение Пологая 62» (enrich.yml) — просто Run workflow.
Локально:  python enrich_pologaya.py
"""

import os
import json
import time

from main import (
    open_page_and_get_data,
    extract_rooms,
    extract_guests,
    extract_area,
    extract_rating,
    extract_reviews,
    extract_price,
)

# Текущая партия на обогащение. Можно переопределить через env IDS="id1,id2".
# 31.10 ОБЩИЙ прогон хвостов (скрипт тащит и "address"):
#  Океан 46 (13 ручных) + Суханова 13 (2) + Фокина 31 (13, нужны адреса).
DEFAULT_IDS = [
    # Океан 46 (ручные):
    "1031413", "1874657", "1043871", "1619750", "2069422", "1844370",
    "974779", "792937", "2060852", "2034609", "1171461", "1570811", "1293011",
    # Суханова 13 (перенос с Фокина):
    "1246955", "923923",
    # Фокина 31 (адреса):
    "1388269", "1792419", "2098192", "929527", "2021345", "2022517",
    "1547129", "1413923", "956995", "774361", "1220955", "2078622", "2087579",
]

IDS = [x.strip() for x in os.environ.get("IDS", "").split(",") if x.strip()] or DEFAULT_IDS

PAUSE = 3  # пауза между объявлениями, сек


import re as _re


def extract_address(page_title):
    """Адрес из заголовка вкладки Суточно:
    '...посуточно, Владивосток, <Улица, дом>, объявление <id> — Суточно.ру'
    -> '<Улица, дом>'."""
    pt = " ".join((page_title or "").split())
    m = _re.search(r"Владивосток,\s*(.*?),\s*объявление", pt)
    if m:
        return m.group(1).strip()
    # запасной вариант: до ' — Суточно'
    m = _re.search(r"Владивосток,\s*(.*?)\s*[—-]\s*Суточно", pt)
    return m.group(1).strip() if m else ""


def enrich_one(oid):
    url = "https://sutochno.ru/front/searchapp/detail/" + oid
    data = open_page_and_get_data(url)
    body = data.get("body_text", "") or ""
    page_title = data.get("page_title", "") or ""
    title = (data.get("title") or page_title or "").strip()
    # title со страницы иногда = служебный заголовок вкладки; чистим переносы
    title = " ".join(title.split())
    try:
        price = extract_price(body)
    except Exception:
        price = ""
    return {
        "id": oid,
        "url": url,
        "title": title[:120],
        "address": extract_address(page_title),
        "rooms": extract_rooms(body),
        "guests": extract_guests(body),
        "area": extract_area(body),
        "rating": extract_rating(body),
        "reviews": extract_reviews(body),
        "price": price,
        "status": data.get("status"),
        "body_len": len(body),
    }


def main():
    rows = []
    for i, oid in enumerate(IDS, 1):
        print(f"[{i}/{len(IDS)}] {oid} ...", flush=True)
        try:
            row = enrich_one(oid)
        except Exception as e:
            row = {"id": oid, "error": type(e).__name__ + ": " + str(e)[:150]}
        print("   ", json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
        if i < len(IDS):
            time.sleep(PAUSE)

    print("\nРЕЗУЛЬТАТ (копируй весь блок ниже):")
    print("<<<ENRICH")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print("ENRICH>>>")


if __name__ == "__main__":
    main()

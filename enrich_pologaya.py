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
# 31.10: 50 кандидатов по Русская 51В (поиск Суточно, студии/1-комн, Вторая Речка).
DEFAULT_IDS = [
    "1183903", "1268853", "1317091", "1374027", "1469285", "1492666",
    "1494178", "1579332", "1591879", "1616761", "1622614", "1650407",
    "1704257", "1713075", "1732221", "1734792", "1763263", "1783776",
    "1789404", "1799088", "1821761", "1839488", "1850705", "1859018",
    "1862812", "1954987", "2012117", "2053130", "2069101", "2071832",
    "2091679", "2100298", "2106320", "2123624", "2128106", "2133347",
    "2154980", "2184504", "2192586", "2276558", "2281582", "2285658",
    "2299659", "2339058", "2343899", "2351859", "2364349", "682357",
    "912199", "994231",
]

IDS = [x.strip() for x in os.environ.get("IDS", "").split(",") if x.strip()] or DEFAULT_IDS

PAUSE = 3  # пауза между объявлениями, сек


def enrich_one(oid):
    url = "https://sutochno.ru/front/searchapp/detail/" + oid
    data = open_page_and_get_data(url)
    body = data.get("body_text", "") or ""
    title = (data.get("title") or data.get("page_title") or "").strip()
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

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
# 31.10: 50 кандидатов по Нейбута 34 (поиск Суточно, 1-комн/студии, р-н Нейбута)
# + 3 ручных для Русская 51В (дозаполнение): 1495506, 2381735, 1541247.
DEFAULT_IDS = [
    "1094905", "1108783", "1388269", "1477587", "1493529", "1514578",
    "1521138", "1522861", "1559542", "1569694", "1585982", "1797291",
    "1826961", "1835555", "1842859", "1863646", "1872960", "1905893",
    "1909621", "1940742", "1957396", "2022554", "2036892", "2079724",
    "2087579", "2115682", "2126490", "2136836", "2154929", "2157157",
    "2170978", "2217750", "2293170", "2310722", "2323258", "2333424",
    "2346676", "2364999", "2369239", "2372971", "788481", "832941",
    "856853", "876875", "898205", "910061", "924131", "939873",
    "948333", "997185",
    # ручные для Русская 51В:
    "1495506", "2381735", "1541247",
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

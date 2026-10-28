import time
import requests
import re

from main import (
    open_page_and_get_data,
    extract_rating,
    extract_reviews,
    extract_guests,
    extract_rooms,
    extract_area,
    extract_floor,
    extract_superhost,
    calculate_price_by_calendar,
)

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbyoOBbl3lKlM2j2ih_5fnsiqJcK5P9KTpmjoJQ59cv5hZB0sxv962yqUvr6Gy1W0nMW/exec"
TOKEN = "sutochno_secret_123"

GUESTS = 4
NIGHTS = 2
OFFSETS = [7, 14, 30]


def normalize_sutochno_url(url):
    """
    Превращает ссылку из приложения Суточно:
    https://sutochno.ru/front/searchapp/detail/1395027
    в нормальную ссылку:
    https://sutochno.ru/1395027
    """

    if not url:
        return url

    match = re.search(r"/detail/(\d+)", url)

    if match:
        object_id = match.group(1)
        return f"https://sutochno.ru/{object_id}"

    match = re.search(r"sutochno\.ru/(\d+)", url)

    if match:
        object_id = match.group(1)
        return f"https://sutochno.ru/{object_id}"

    return url


def post_to_sheet(payload):
    response = requests.post(WEB_APP_URL, json=payload, timeout=180)

    print("\n--- GOOGLE SCRIPT RESPONSE DEBUG ---")
    print("Action:", payload.get("action"))
    print("Status code:", response.status_code)
    print("Content-Type:", response.headers.get("content-type"))
    print("Response start:", response.text[:500])
    print("--- END DEBUG ---\n")

    response.raise_for_status()

    try:
        return response.json()
    except Exception:
        raise RuntimeError(
            "Google Apps Script вернул не JSON. "
            "Скорее всего, ошибка в Apps Script или не обновлено развертывание. "
            f"Первые 500 символов ответа: {response.text[:500]}"
        )


def get_competitors():
    result = post_to_sheet({
        "token": TOKEN,
        "action": "getCompetitors"
    })

    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Ошибка получения конкурентов"))

    return result.get("competitors", [])


def parse_competitor(competitor):
    url = normalize_sutochno_url(competitor["url"])
    competitor_id = competitor["id"]

    title = ""
    rating = ""
    reviews = ""
    max_guests = ""
    rooms = ""
    area = ""
    floor = ""
    superhost = False
    common_error = ""

    try:
        page_data = open_page_and_get_data(url)
        text = page_data["body_text"]

        title = page_data.get("title", "")
        rating = extract_rating(text)
        reviews = extract_reviews(text)
        max_guests = extract_guests(text)
        rooms = extract_rooms(text)
        area = extract_area(text)
        floor = extract_floor(text)
        superhost = extract_superhost(text)

    except Exception as error:
        common_error = str(error)

    results = []

    for offset in OFFSETS:
        try:
            price_data = calculate_price_by_calendar(
                url=url,
                offset=offset,
                guests=GUESTS,
                nights=NIGHTS
            )

            results.append({
                "offset": offset,
                "check_in": price_data.get("check_in"),
                "check_out": price_data.get("check_out"),
                "nights": NIGHTS,
                "total_price": price_data.get("total_price"),
                "price": price_data.get("price_per_night"),
                "available": price_data.get("available"),
                "error": price_data.get("error", "")
            })

        except Exception as error:
            results.append({
                "offset": offset,
                "check_in": "",
                "check_out": "",
                "nights": NIGHTS,
                "total_price": None,
                "price": None,
                "available": False,
                "error": str(error)
            })

        time.sleep(2)

    return {
        "id": competitor_id,
        "url": url,
        "guests": GUESTS,
        "nights": NIGHTS,
        "title": title,
        "address": "",
        "rooms": rooms,
        "max_guests": max_guests,
        "area": area,
        "floor": floor,
        "superhost": superhost,
        "rating": rating,
        "reviews": reviews,
        "results": results,
        "error": common_error
    }


def update_competitor(row_number, competitor_id, data):
    return post_to_sheet({
        "token": TOKEN,
        "action": "updateCompetitor",
        "rowNumber": row_number,
        "id": competitor_id,
        "data": data
    })


def recalculate_recommendations():
    return post_to_sheet({
        "token": TOKEN,
        "action": "calculateRecommendations"
    })


def save_price_history():
    return post_to_sheet({
        "token": TOKEN,
        "action": "savePriceHistory"
    })


def main():
    print("Получаю список конкурентов из Google Таблицы...")
    competitors = get_competitors()

    print(f"Найдено активных конкурентов: {len(competitors)}")

    if not competitors:
        print("Нет активных конкурентов. Проверь вкладку Конкуренты.")
        return

    for index, competitor in enumerate(competitors, start=1):
        print(f"\n[{index}/{len(competitors)}] Проверяю: {competitor['url']}")

        data = parse_competitor(competitor)

        update_result = update_competitor(
            row_number=competitor["rowNumber"],
            competitor_id=competitor["id"],
            data=data
        )

        if update_result.get("ok"):
            print("Готово. Данные записаны в таблицу.")
        else:
            print("Ошибка записи:", update_result)

        time.sleep(3)

    print("\nСохраняю историю цен...")
    save_price_history()

    print("\nПересчитываю рекомендации...")
    recalculate_recommendations()

    print("\nГотово. Таблица обновлена.")


if __name__ == "__main__":
    main()
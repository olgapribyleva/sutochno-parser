"""
ЦЕНОВОЙ ПАРСЕР КОНКУРЕНТОВ — ЕДИНАЯ АВТОНОМНАЯ СИСТЕМА (все квартиры).

Как парсер Фокина 31 (update_sheet.py), но для любой квартиры: берёт список
конкурентов ИЗ Google-таблицы «Отбор конкурентов по квартирам» через её
Apps Script Web App, парсит цену за ночь на 3 даты (+7/+14/+30, 2 ночи) и
пишет цены обратно в лист этой квартиры. Рекомендации считает сам Web App
(action 'calculateRecommendations').

ПОЛНЫЙ АВТОМАТ: запускается GitHub Actions по расписанию (пн и чт), пишет
через Web App под аккаунтом Ольги — Клодик в прогоне не участвует.

Какая квартира парсится — задаётся env APARTMENT (ключ из листа «Настройки цен»).
В воркфлоу это матрица: по заданию на каждую квартиру параллельно.

Запуск: APARTMENT=sukhanova13 python prices_run.py
Пересчёт рекомендаций отдельно: ACTION=recommend python prices_run.py
"""

import os
import time
import re
import requests

# ВАЖНО: main/update_sheet тянут Playwright. Импортируем их ЛЕНИВО внутри
# парсящих функций, чтобы задача пересчёта рекомендаций (ACTION=recommend)
# работала без установки браузера.

# Web App таблицы «Отбор конкурентов по квартирам» (НОВЫЙ, боундед к этой книге).
# ⚠️ ПОДСТАВИТЬ после деплоя скрипта Ольгой (New deployment → Web app → /exec).
WEB_APP_URL = os.environ.get("PRICES_WEB_APP_URL", "PASTE_PRICES_WEB_APP_URL_HERE")
TOKEN = os.environ.get("PRICES_TOKEN", "sutochno_prices_123")

# Как на Фокина 31.
OFFSETS = [7, 14, 30]
NIGHTS = 2
# Пробуем сначала 2 ночи, при неудаче — 3 ночи: у части конкурентов минимум
# проживания 3 ночи, и запрос на 2 ночи у них не даёт цену. Фоллбэк на 3 ночи
# вытаскивает такие объекты (цену всё равно считаем за ночь).
NIGHTS_TRY = [2, 3]
PAUSE = 3  # пауза между объектами, сек

# Число гостей под профиль квартиры (цена на Суточно зависит от гостей).
GUESTS_BY_APARTMENT = {
    "fokina31": 4,
    "pologaya62": 5,
    "sukhanova13": 4,
    "russkaya51v": 2,
    "neibuta34": 2,
    "neibuta2a": 4,
    "ocean46": 4,
}


def post(payload, timeout=180):
    r = requests.post(WEB_APP_URL, json=payload, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        raise RuntimeError("Web App вернул не JSON: " + r.text[:400])


def post_retry(payload, attempts=4, base_delay=5, timeout=180):
    """POST в Web App с ретраями на ВРЕМЕННЫХ сбоях.

    Повторяет при: сетевых ошибках, таймаутах, кодах 5xx/429 и ответе-не-JSON
    (Apps Script при холодном старте иногда отдаёт HTML-страницу логина).
    Успехом считается ТОЛЬКО ответ-JSON с ok=true. Если за `attempts` попыток
    ok=true не пришёл — бросает RuntimeError (джоба упадёт КРАСНОЙ и будет видно,
    а не «зелёной» с необновлённым листом, как было раньше)."""
    last_err = None
    for i in range(1, attempts + 1):
        try:
            res = post(payload, timeout=timeout)
            if res.get("ok"):
                return res
            last_err = "ok=false: " + str(res.get("error") or res)[:300]
        except requests.HTTPError as e:
            code = getattr(getattr(e, "response", None), "status_code", 0) or 0
            last_err = "HTTP " + str(code)
            if code and code < 500 and code != 429:
                raise  # клиентская ошибка (кроме 429) — ретрай не поможет
        except (requests.ConnectionError, requests.Timeout, RuntimeError) as e:
            last_err = (type(e).__name__ + ": " + str(e))[:300]
        if i < attempts:
            delay = base_delay * i  # 5, 10, 15 сек
            print("   ⟳ попытка %d/%d не удалась (%s); жду %dс" % (i, attempts, last_err, delay), flush=True)
            time.sleep(delay)
    raise RuntimeError("Web App не вернул ok за %d попыток: %s" % (attempts, last_err))


def get_competitors(apartment):
    res = post({"token": TOKEN, "action": "getCompetitors", "apartment": apartment})
    if not res.get("ok"):
        raise RuntimeError(res.get("error", "getCompetitors error"))
    return res.get("competitors", [])


def normalize_sutochno_url(url):
    """/detail/<id> -> sutochno.ru/<id> (копия из update_sheet, без тяжёлых импортов)."""
    if not url:
        return url
    m = re.search(r"/detail/(\d+)", url)
    if m:
        return "https://sutochno.ru/" + m.group(1)
    m = re.search(r"sutochno\.ru/(\d+)", url)
    if m:
        return "https://sutochno.ru/" + m.group(1)
    return url


def price_point(url, offset, guests):
    """Цена по одному горизонту. Пробует 2 ночи, при неудаче — 3 ночи.
    Возвращает первую попытку, где нашлась цена; иначе — последнюю (с ошибкой)."""
    from main import calculate_price_by_calendar
    last = {
        "offset": offset, "check_in": "", "price": None, "total": None,
        "available": False, "error": "", "nights": None,
    }
    for nights in NIGHTS_TRY:
        try:
            pd = calculate_price_by_calendar(url=url, offset=offset, guests=guests, nights=nights)
            res = {
                "offset": offset,
                "check_in": pd.get("check_in"),
                "price": pd.get("price_per_night"),
                "total": pd.get("total_price"),
                "available": bool(pd.get("available")),
                "error": pd.get("error", "") or "",
                "nights": nights,
            }
            if res["available"] and res["price"]:
                return res   # нашли цену — дальше не пробуем
            last = res       # запомним и попробуем 3 ночи
        except Exception as e:
            last = {
                "offset": offset, "check_in": "", "price": None, "total": None,
                "available": False, "nights": nights,
                "error": (type(e).__name__ + ": " + str(e))[:150],
            }
        time.sleep(2)
    return last


def price_points(url, guests):
    results = []
    for offset in OFFSETS:
        results.append(price_point(url, offset, guests))
    return results


def run_apartment(apartment):
    guests = GUESTS_BY_APARTMENT.get(apartment, 4)
    comps = get_competitors(apartment)
    print(f"Квартира {apartment}: конкурентов {len(comps)}, гостей {guests}", flush=True)

    for i, c in enumerate(comps, 1):
        url = normalize_sutochno_url(c.get("url") or "")
        print(f"[{i}/{len(comps)}] row {c.get('rowNumber')} id {c.get('id')} {url}", flush=True)
        results = price_points(url, guests)
        nums = [p["price"] for p in results if isinstance(p.get("price"), (int, float)) and p["price"]]
        prices = [p["price"] for p in results]
        avail = [p["available"] for p in results]
        print("   prices:", prices, "avail:", avail, flush=True)
        try:
            upd = post({
                "token": TOKEN, "action": "updateCompetitor",
                "apartment": apartment, "rowNumber": c.get("rowNumber"), "id": c.get("id"),
                "data": {"results": results},
            })
            if not upd.get("ok"):
                print("   ⚠ update error:", upd, flush=True)
        except Exception as e:
            print("   ⚠ update exception:", repr(e), flush=True)
        if i < len(comps):
            time.sleep(PAUSE)

    print(f"Квартира {apartment}: готово.", flush=True)


def recommend_all():
    print("Пересчёт рекомендаций по всем квартирам...", flush=True)
    # Пауза: даём Web App «остыть» после параллельной записи цен 7 квартирами.
    time.sleep(10)
    # С ретраями и проверкой ok — иначе разовый сбой Web App раньше проглатывался,
    # джоба была зелёной, а лист «Рекомендации» оставался старым (сбой 05.11 и 09.11).
    r1 = post_retry({"token": TOKEN, "action": "savePriceHistory"})
    print("savePriceHistory:", r1, flush=True)
    r2 = post_retry({"token": TOKEN, "action": "calculateRecommendations"})
    print("calculateRecommendations:", r2, flush=True)
    # Сюда дойдём ТОЛЬКО если обе операции вернули ok=true (иначе post_retry бросил).
    print("✅ Рекомендации пересчитаны, лист обновлён:", r2.get("updated"), flush=True)


def main():
    action = (os.environ.get("ACTION", "") or "").strip().lower()
    if action == "recommend":
        recommend_all()
        return
    apartment = (os.environ.get("APARTMENT", "") or "").strip().lower()
    if not apartment:
        raise SystemExit("Не задан APARTMENT (ключ квартиры) и ACTION != recommend.")
    run_apartment(apartment)


if __name__ == "__main__":
    main()

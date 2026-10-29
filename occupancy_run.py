"""
ПОЛНЫЙ ПРОГОН ЗАНЯТОСТИ по всем активным конкурентам → Google Таблица.

Читает занятость (свободно/занято по дням) каждого активного конкурента
через браузер (read_calendar_occupancy) и отправляет единым пакетом в
Apps Script Web App (action 'saveOccupancy'), который раскладывает данные
в лист «Занятость конкурентов» (строка = конкурент, столбец = дата).

Использует тот же WEB_APP_URL и TOKEN, что и update_sheet.py — нужно лишь
добавить в Web App обработчик action 'saveOccupancy' (см. occupancy-webapp-action.gs)
и переразвернуть (Deploy → Manage deployments → Edit → New version).

Запуск: workflow «Занятость конкурентов» (occupancy.yml) или локально.
"""

import time
import requests

from main import read_calendar_occupancy
from update_sheet import (
    WEB_APP_URL,
    TOKEN,
    get_competitors,
    normalize_sutochno_url,
)

# Сколько месячных экранов календаря листать (≈ months месяцев вперёд).
MONTHS = 3

# Пауза между объектами, чтобы Суточно не притормаживал (сек).
PAUSE = 4


def post_occupancy(competitors_payload):
    resp = requests.post(
        WEB_APP_URL,
        json={
            "token": TOKEN,
            "action": "saveOccupancy",
            "competitors": competitors_payload,
        },
        timeout=180,
    )
    print("Web App:", resp.status_code, resp.text[:300])
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        raise RuntimeError("Web App вернул не JSON (проверь, что добавлен action saveOccupancy и сделан редеплой).")


def main():
    print("Беру список конкурентов...")
    competitors = get_competitors()
    print(f"Активных конкурентов: {len(competitors)}")

    payload = []
    ok_count = 0

    for i, comp in enumerate(competitors, start=1):
        url = normalize_sutochno_url(comp["url"])
        try:
            res = read_calendar_occupancy(url, months=MONTHS)
        except Exception as e:
            res = {"ok": False, "error": repr(e), "occupancy": [], "free": None, "busy": None}

        days = {x["date"]: x["status"] for x in res.get("occupancy", [])}
        if res.get("ok"):
            ok_count += 1

        payload.append({
            "id": comp.get("id"),
            "name": comp.get("name") or comp.get("url"),
            "ok": bool(res.get("ok")),
            "free": res.get("free"),
            "busy": res.get("busy"),
            "error": (res.get("error", "") or "")[:200],
            "days": days,
        })

        print(f"[{i}/{len(competitors)}] {url} ok={res.get('ok')} free={res.get('free')} busy={res.get('busy')}")
        time.sleep(PAUSE)

    print(f"\nУспешно прочитано: {ok_count}/{len(competitors)}. Отправляю в таблицу...")
    result = post_occupancy(payload)
    print("Результат:", result)
    print("Готово.")


if __name__ == "__main__":
    main()

"""
ПОЛНЫЙ ПРОГОН ЗАНЯТОСТИ по всем активным конкурентам → Google Таблица.

Читает занятость (свободно/занято по дням) каждого активного конкурента
через браузер (read_calendar_occupancy) и отправляет единым пакетом в
Apps Script Web App (action 'saveOccupancy'), который раскладывает данные
в лист «Занятость конкурентов» (строка = конкурент, столбец = дата).

НАДЁЖНОСТЬ: после основного прохода делаем до MAX_RETRY_PASSES повторных
проходов ТОЛЬКО по тем, у кого календарь не открылся, с увеличенной паузой
(у Суточно при 30 запросах подряд срабатывает троттлинг). Повтор заменяет
результат, только если он успешный, — иначе остаётся прежний.

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

# Пауза между объектами в основном проходе (сек).
PAUSE = 6

# Пауза между объектами в ПОВТОРНЫХ проходах (больше — снимаем троттлинг).
RETRY_PAUSE = 12

# Сколько повторных проходов делать по не открывшимся.
MAX_RETRY_PASSES = 1


def read_one(comp):
    """Прочитать занятость одного конкурента. Возвращает (url, res)."""
    url = normalize_sutochno_url(comp["url"])
    try:
        res = read_calendar_occupancy(url, months=MONTHS)
    except Exception as e:
        res = {"ok": False, "error": repr(e), "occupancy": [], "free": None, "busy": None}
    return url, res


def build_entry(comp, res):
    days = {x["date"]: x["status"] for x in res.get("occupancy", [])}
    return {
        "id": comp.get("id"),
        "name": comp.get("name") or comp.get("url"),
        "ok": bool(res.get("ok")),
        "free": res.get("free"),
        "busy": res.get("busy"),
        "error": (res.get("error", "") or "")[:200],
        "days": days,
    }


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
    total = len(competitors)
    print(f"Активных конкурентов: {total}")

    # основной проход
    results = {}  # index -> (comp, res)
    for i, comp in enumerate(competitors):
        url, res = read_one(comp)
        results[i] = (comp, res)
        print(f"[{i + 1}/{total}] {url} ok={res.get('ok')} free={res.get('free')} busy={res.get('busy')}")
        time.sleep(PAUSE)

    # повторные проходы только по не открывшимся
    for p in range(MAX_RETRY_PASSES):
        failed = [i for i, (c, r) in results.items() if not r.get("ok")]
        if not failed:
            break
        print(f"\n=== Повторный проход {p + 1}/{MAX_RETRY_PASSES}: не открылись {len(failed)} — пробую снова (пауза {RETRY_PAUSE}с) ===")
        for i in failed:
            comp = results[i][0]
            url, res = read_one(comp)
            if res.get("ok"):
                results[i] = (comp, res)
                print(f"  ↻ УДАЛОСЬ: {url} free={res.get('free')} busy={res.get('busy')}")
            else:
                print(f"  ✗ снова не открылся: {url}")
            time.sleep(RETRY_PAUSE)

    ok_count = sum(1 for i, (c, r) in results.items() if r.get("ok"))
    payload = [build_entry(c, r) for i, (c, r) in sorted(results.items())]

    print(f"\nУспешно прочитано: {ok_count}/{total}. Отправляю в таблицу...")
    result = post_occupancy(payload)
    print("Результат:", result)
    print("Готово.")


if __name__ == "__main__":
    main()

"""
ТЕСТ ЗАНЯТОСТИ (probe) — часть апгрейда парсера.

Читает занятость по дням (свободно/занято) для первых нескольких активных
конкурентов и печатает КОМПАКТНЫЙ результат в лог. Логи GitHub Actions легко
скопировать, поэтому Apps Script/редеплой для теста не нужны.

Запуск: вручную через workflow «Тест занятости» (occupancy-test.yml)
или локально: python occupancy_probe.py
"""

import json

from main import read_calendar_occupancy
from update_sheet import get_competitors, normalize_sutochno_url

# Сколько конкурентов проверить в тесте (не перегружаем).
LIMIT = 2

# Сколько месячных экранов календаря листать.
MONTHS = 3


def short(occ_result):
    """Короткая сводка результата занятости для лога."""
    return {
        "ok": occ_result.get("ok"),
        "days_total": occ_result.get("days_total"),
        "free": occ_result.get("free"),
        "busy": occ_result.get("busy"),
        "error": occ_result.get("error", ""),
        # первые/последние даты — чтобы увидеть, какой период охвачен
        "first_days": [x for x in occ_result.get("occupancy", [])[:6]],
        "last_days": [x for x in occ_result.get("occupancy", [])[-4:]],
        # сырые ячейки — чтобы проверить, верно ли распознаём классы календаря
        "raw_sample": occ_result.get("raw_sample", [])[:12],
    }


def main():
    print("=== ТЕСТ ЗАНЯТОСТИ: беру список конкурентов ===")
    competitors = get_competitors()
    print(f"Активных конкурентов: {len(competitors)}")

    picked = competitors[:LIMIT]

    for i, comp in enumerate(picked, start=1):
        url = normalize_sutochno_url(comp["url"])
        print(f"\n----- [{i}/{len(picked)}] {url} -----")
        try:
            res = read_calendar_occupancy(url, months=MONTHS)
        except Exception as e:
            print("ОШИБКА:", repr(e))
            continue

        print("РЕЗУЛЬТАТ (копируй весь блок ниже):")
        print("<<<OCC")
        print(json.dumps(short(res), ensure_ascii=False, indent=2))
        print("OCC>>>")


if __name__ == "__main__":
    main()

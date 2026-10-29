from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import re
import time

from playwright.sync_api import sync_playwright


app = FastAPI(title="Sutochno Parser")


class ParseRequest(BaseModel):
    id: Optional[Any] = None
    url: str
    guests: int = 4
    nights: int = 2
    offsets: List[int] = [7, 14, 30]


def clean_price(text):
    if not text:
        return None

    digits = re.sub(r"[^\d]", "", str(text))

    if not digits:
        return None

    price = int(digits)

    if price < 1000 or price > 100000:
        return None

    return price


def find_price_candidates(text):
    patterns = [
        r".{0,60}от\s*([\d\s]+)\s*₽.{0,60}",
        r".{0,60}([\d\s]+)\s*₽\s*/?\s*сут.{0,60}",
        r".{0,60}([\d\s]+)\s*₽.{0,60}"
    ]

    candidates = []

    for pattern in patterns:
        matches = re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL)

        for match in matches:
            full_fragment = match.group(0)
            price_text = match.group(1)
            price = clean_price(price_text)

            if price and 1000 <= price <= 100000:
                candidates.append({
                    "price": price,
                    "fragment": " ".join(full_fragment.split())
                })

    return candidates


def find_price_candidates(text):
    patterns = [
        r".{0,60}от\s*([\d\s]+)\s*₽.{0,60}",
        r".{0,60}([\d\s]+)\s*₽\s*/?\s*сут.{0,60}",
        r".{0,60}([\d\s]+)\s*₽.{0,60}"
    ]

    candidates = []

    for pattern in patterns:
        matches = re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL)

        for match in matches:
            full_fragment = match.group(0)
            price_text = match.group(1)
            price = clean_price(price_text)

            if price and 1000 <= price <= 100000:
                candidates.append({
                    "price": price,
                    "fragment": " ".join(full_fragment.split())
                })

    return candidates


def extract_calculated_price(text, nights):
    """
    Ищет именно расчетную стоимость проживания:
    пример: 15 000 ₽ за 2 суток
    Возвращает общую цену за весь период.
    """

    if not text:
        return None

    # Убираем неразрывные пробелы и нормализуем текст
    normalized = (
        text.replace("\xa0", " ")
            .replace("\u202f", " ")
            .replace("\n", " ")
            .replace("\r", " ")
    )

    # Сначала ищем точное совпадение: "15 000 ₽ за 2 суток"
    patterns = [
        rf"([\d\s]+)\s*₽\s*за\s*{int(nights)}\s*сут",
        rf"([\d\s]+)\s*₽\s*за\s*{int(nights)}\s*ноч",
        r"([\d\s]+)\s*₽\s*за\s*\d+\s*сут",
        r"([\d\s]+)\s*₽\s*за\s*\d+\s*ноч"
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            price = clean_price(match.group(1))
            if price and price >= 1000:
                return price

    # Резервный вариант: ищем фрагменты с "за ... суток"
    candidates = find_price_candidates(normalized)

    for item in candidates:
        fragment = item.get("fragment", "").lower()
        price = item.get("price")

        if not price:
            continue

        if "за 2 сут" in fragment or "за 2 ноч" in fragment:
            return price

        if "за 3 сут" in fragment or "за 3 ноч" in fragment:
            return price

        if "за 4 сут" in fragment or "за 4 ноч" in fragment:
            return price

    return None


def extract_prepaid_price(text):
    """
    Ищет предоплату, но она нам НЕ нужна для цены проживания.
    Оставляем для диагностики.
    """
    match = re.search(r"([\d\s]+)\s*₽\s*оплатить сейчас", text, flags=re.IGNORECASE)
    if match:
        return clean_price(match.group(1))
    return None


def extract_price(text):
    candidates = find_price_candidates(text)

    if not candidates:
        return None

    # Убираем заведомо мусорные фрагменты
    bad_words = [
        "кэшбэк",
        "депозит",
        "залог",
        "скидк",
        "избранное",
        "гост",
        "м2",
        "этаж",
        "отзыв"
    ]

    clean_candidates = []

    for item in candidates:
        fragment = item["fragment"].lower()

        if any(word in fragment for word in bad_words):
            continue

        clean_candidates.append(item)

    if clean_candidates:
        return clean_candidates[0]["price"]

    return candidates[0]["price"]


def extract_rating(text):
    match = re.search(r"\n(\d+[.,]\d+)\n\d+\s+отзыв", text, re.IGNORECASE)
    if not match:
        match = re.search(r"(\d+[.,]\d+)", text)
    if not match:
        return ""
    return match.group(1).replace(",", ".")


def extract_reviews(text):
    match = re.search(r"(\d+)\s+отзыв", text, re.IGNORECASE)
    if not match:
        return ""
    return int(match.group(1))


def extract_guests(text):
    match = re.search(r"(\d+)\s+гост", text, re.IGNORECASE)
    if not match:
        return ""
    return int(match.group(1))


def extract_rooms(text):
    match = re.search(r"(\d+)[-\s]?комнат", text, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1)


def extract_area(text):
    match = re.search(r"(\d+)\s*м2", text, re.IGNORECASE)
    if not match:
        return ""
    return int(match.group(1))


def extract_floor(text):
    match = re.search(r"(\d+)\s+из\s+(\d+)", text, re.IGNORECASE)
    if not match:
        return ""
    return match.group(0)


def extract_superhost(text):
    return "Суперхозяин" in text


def build_url_with_params(url, check_in, check_out, guests):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    query["date_begin"] = [check_in.isoformat()]
    query["date_end"] = [check_out.isoformat()]
    query["guests"] = [str(guests)]
    query["adults"] = [str(guests)]

    new_query = urlencode(query, doseq=True)

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))


def open_page_and_get_data(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(10000)

        status = response.status if response else None
        current_url = page.url
        page_title = page.title()

        try:
            body_text = page.locator("body").inner_text(timeout=10000)
        except Exception as e:
            body_text = "BODY_ERROR: " + repr(e)

        try:
            html = page.content()
        except Exception as e:
            html = "HTML_ERROR: " + repr(e)

        title = ""
        try:
            title = page.locator("h1").first.inner_text(timeout=3000)
        except Exception:
            title = page_title

        browser.close()

        return {
            "status": status,
            "current_url": current_url,
            "page_title": page_title,
            "title": title,
            "body_text": body_text,
            "html": html
        }


@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "Парсер работает"
    }


@app.post("/debug-sutochno")
def debug_sutochno(request: ParseRequest):
    try:
        data = open_page_and_get_data(request.url)
        body_text = data["body_text"]
        html = data["html"]

        return {
         "ok": True,
         "status": data["status"],
         "current_url": data["current_url"],
         "page_title": data["page_title"],
         "title": data["title"],
         "text_length": len(body_text),
         "text_start": body_text[:3000],
         "price_candidates": find_price_candidates(body_text)[:20],
         "html_start": html[:1500]
        }

    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error_text": str(e),
            "error_repr": repr(e)
        }


@app.post("/debug-price-url")
def debug_price_url(request: ParseRequest):
    try:
        today = date.today()
        results = []

        for offset in request.offsets:
            check_in = today + timedelta(days=offset)
            nights = max(int(request.nights or 2), 2)
            check_out = check_in + timedelta(days=nights)

            test_url = build_url_with_params(
                request.url,
                check_in,
                check_out,
                request.guests
            )

            try:
                data = open_page_and_get_data(test_url)
                text = data["body_text"]

                results.append({
                    "offset": offset,
                    "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat(),
                    "test_url": test_url,
                    "page_title": data.get("page_title", ""),
                    "current_url": data.get("current_url", ""),
                    "text_length": len(text),
                    "price_candidates": find_price_candidates(text)[:20],
                    "text_start": text[:1500]
                })

            except Exception as inner_error:
                results.append({
                    "offset": offset,
                    "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat(),
                    "test_url": test_url,
                    "error_type": type(inner_error).__name__,
                    "error_text": str(inner_error),
                    "error_repr": repr(inner_error)
                })

        return {
            "ok": True,
            "results": results
        }

    except Exception as outer_error:
        return {
            "ok": False,
            "error_type": type(outer_error).__name__,
            "error_text": str(outer_error),
            "error_repr": repr(outer_error)
        }


@app.post("/debug-elements")
def debug_elements(request: ParseRequest):
    try:
        data = open_page_and_get_data(request.url)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

            context = browser.new_context(
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )

            page = context.new_page()
            page.goto(request.url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000)

            buttons = []
            inputs = []

            button_locators = page.locator("button").all()
            for i, btn in enumerate(button_locators[:80]):
                try:
                    text = btn.inner_text(timeout=1000)
                    html = btn.evaluate("el => el.outerHTML")
                    buttons.append({
                        "index": i,
                        "text": " ".join(text.split())[:300],
                        "html": html[:500]
                    })
                except Exception:
                    pass

            input_locators = page.locator("input").all()
            for i, inp in enumerate(input_locators[:80]):
                try:
                    value = inp.get_attribute("value")
                    placeholder = inp.get_attribute("placeholder")
                    input_type = inp.get_attribute("type")
                    name = inp.get_attribute("name")
                    input_id = inp.get_attribute("id")
                    html = inp.evaluate("el => el.outerHTML")
                    inputs.append({
                        "index": i,
                        "type": input_type,
                        "name": name,
                        "id": input_id,
                        "placeholder": placeholder,
                        "value": value,
                        "html": html[:500]
                    })
                except Exception:
                    pass

            body_text = page.locator("body").inner_text(timeout=10000)

            browser.close()

            return {
                "ok": True,
                "current_url": data["current_url"],
                "page_title": data["page_title"],
                "buttons_count": len(buttons),
                "inputs_count": len(inputs),
                "buttons": buttons,
                "inputs": inputs,
                "text_start": body_text[:2000]
            }

    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error_text": str(e),
            "error_repr": repr(e)
        }


@app.post("/debug-fill-dates")
def debug_fill_dates(request: ParseRequest):
    try:
        today = date.today()
        results = []

        for offset in request.offsets:
            check_in = today + timedelta(days=offset)
            nights = max(int(request.nights or 2), 2)
            check_out = check_in + timedelta(days=nights)

            # Формат для Суточно: дд.мм
            check_in_short = check_in.strftime("%d.%m")
            check_out_short = check_out.strftime("%d.%m")

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )

                context = browser.new_context(
                    viewport={"width": 1366, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                )

                page = context.new_page()
                page.goto(request.url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)

                # Закрываем cookies, если есть
                try:
                    page.locator("#modal-cookies-accept").click(timeout=2000)
                    page.wait_for_timeout(1000)
                except Exception:
                    pass

                # Вставляем даты напрямую через JavaScript
                page.evaluate(
                    """([arrival, departure]) => {
                        const arrivalInput = document.querySelector('#arrival-date');
                        const departureInput = document.querySelector('#departure-date');

                        if (arrivalInput) {
                            arrivalInput.value = arrival;
                            arrivalInput.dispatchEvent(new Event('input', { bubbles: true }));
                            arrivalInput.dispatchEvent(new Event('change', { bubbles: true }));
                        }

                        if (departureInput) {
                            departureInput.value = departure;
                            departureInput.dispatchEvent(new Event('input', { bubbles: true }));
                            departureInput.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""",
                    [check_in_short, check_out_short]
                )

                page.wait_for_timeout(1500)

                # Пробуем выбрать 4 гостей через текст
                try:
                    page.get_by_text(str(request.guests), exact=True).nth(0).click(timeout=3000)
                    page.wait_for_timeout(1000)
                except Exception:
                    pass

                # Нажимаем кнопку "Цена и доступность"
                try:
                    page.locator(".js-show-booking-price").click(timeout=5000)
                    page.wait_for_timeout(8000)
                except Exception as click_error:
                    pass

                body_text = page.locator("body").inner_text(timeout=10000)

                object_price = ""
                try:
                    object_price = page.locator("input[name='object_price']").get_attribute("value")
                except Exception:
                    object_price = ""

                arrival_value = ""
                departure_value = ""

                try:
                    arrival_value = page.locator("#arrival-date").get_attribute("value")
                except Exception:
                    pass

                try:
                    departure_value = page.locator("#departure-date").get_attribute("value")
                except Exception:
                    pass

                price_candidates = find_price_candidates(body_text)[:30]

                browser.close()

                results.append({
                    "offset": offset,
                    "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat(),
                    "check_in_short": check_in_short,
                    "check_out_short": check_out_short,
                    "arrival_value_after": arrival_value,
                    "departure_value_after": departure_value,
                    "object_price": object_price,
                    "price_candidates": price_candidates,
                    "text_after": body_text[:3000]
                })

        return {
            "ok": True,
            "results": results
        }

    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error_text": str(e),
            "error_repr": repr(e)
        }


@app.post("/debug-calendar")
def debug_calendar(request: ParseRequest):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

            context = browser.new_context(
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )

            page = context.new_page()
            page.goto(request.url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            try:
                page.locator("#modal-cookies-accept").click(timeout=2000)
                page.wait_for_timeout(1000)
            except Exception:
                pass

            # Кликаем по блоку календаря, который перекрывает input
            page.locator(".js-booking-calendar-field").first.click(timeout=10000)
            page.wait_for_timeout(5000)

            body_text = page.locator("body").inner_text(timeout=10000)

            buttons = []
            all_buttons = page.locator("button").all()
            for i, btn in enumerate(all_buttons[:120]):
                try:
                    text = btn.inner_text(timeout=1000)
                    html = btn.evaluate("el => el.outerHTML")
                    buttons.append({
                        "index": i,
                        "text": " ".join(text.split())[:300],
                        "html": html[:500]
                    })
                except Exception:
                    pass

            cells = []
            possible_cells = page.locator("td, .day, .available, .calendar-day, [data-date]").all()
            for i, cell in enumerate(possible_cells[:200]):
                try:
                    text = cell.inner_text(timeout=1000)
                    html = cell.evaluate("el => el.outerHTML")
                    cells.append({
                        "index": i,
                        "text": " ".join(text.split())[:200],
                        "html": html[:500]
                    })
                except Exception:
                    pass

            html = page.content()

            browser.close()

            return {
                "ok": True,
                "text_after_click": body_text[:3000],
                "buttons": buttons,
                "cells": cells[:80],
                "html_start": html[:3000]
            }

    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error_text": str(e),
            "error_repr": repr(e)
        }


@app.post("/debug-select-dates")
def debug_select_dates(request: ParseRequest):
    try:
        today = date.today()
        results = []

        for offset in request.offsets:
            check_in = today + timedelta(days=offset)
            nights = max(int(request.nights or 2), 2)
            check_out = check_in + timedelta(days=nights)

            check_in_day = str(check_in.day)
            check_out_day = str(check_out.day)

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )

                context = browser.new_context(
                    viewport={"width": 1366, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                )

                page = context.new_page()
                page.goto(request.url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)

                try:
                    page.locator("#modal-cookies-accept").click(timeout=2000)
                    page.wait_for_timeout(1000)
                except Exception:
                    pass

                page.locator(".js-booking-calendar-field").first.click(timeout=10000)
                page.wait_for_timeout(3000)

                def snapshot_calendar():
                    items = []
                    cells = page.locator("td").all()
                    for i, cell in enumerate(cells[:120]):
                        try:
                            text = cell.inner_text(timeout=500).strip()
                            html = cell.evaluate("el => el.outerHTML")
                            if text:
                                items.append({
                                    "index": i,
                                    "text": text,
                                    "html": html[:400]
                                })
                        except Exception:
                            pass
                    return items

                before_cells = snapshot_calendar()

                clicked_in = False
                clicked_out = False

                # Кликаем заезд
                cells = page.locator("td.available:not(.disabled)")
                for i in range(cells.count()):
                    cell = cells.nth(i)
                    try:
                        text = cell.inner_text(timeout=1000).strip()
                        if text == check_in_day:
                            cell.click(timeout=3000)
                            clicked_in = True
                            page.wait_for_timeout(1500)
                            break
                    except Exception:
                        pass

                after_first_click_cells = snapshot_calendar()

                # Кликаем выезд
                cells = page.locator("td.available:not(.disabled)")
                for i in range(cells.count()):
                    cell = cells.nth(i)
                    try:
                        text = cell.inner_text(timeout=1000).strip()
                        if text == check_out_day:
                            cell.click(timeout=3000)
                            clicked_out = True
                            page.wait_for_timeout(1500)
                            break
                    except Exception:
                        pass

                after_second_click_cells = snapshot_calendar()

                apply_html = ""
                apply_disabled = ""
                try:
                    apply_html = page.locator(".applyBtn").evaluate("el => el.outerHTML")
                    apply_disabled = page.locator(".applyBtn").get_attribute("disabled")
                except Exception as e:
                    apply_html = "APPLY_ERROR: " + repr(e)

                # Пробуем нажать Apply
                apply_clicked = False
                try:
                    page.locator(".applyBtn").click(timeout=5000)
                    apply_clicked = True
                    page.wait_for_timeout(4000)
                except Exception:
                    pass

                after_apply_text = page.locator("body").inner_text(timeout=10000)

                # Потом пробуем кнопку цена
                price_button_clicked = False
                try:
                    page.locator(".js-show-booking-price").click(timeout=5000)
                    price_button_clicked = True
                    page.wait_for_timeout(8000)
                except Exception:
                    pass

                body_text = page.locator("body").inner_text(timeout=10000)

                object_price = ""
                try:
                    object_price = page.locator("input[name='object_price']").get_attribute("value")
                except Exception:
                    pass

                arrival_value = ""
                departure_value = ""

                try:
                    arrival_value = page.locator("#arrival-date").get_attribute("value")
                except Exception:
                    pass

                try:
                    departure_value = page.locator("#departure-date").get_attribute("value")
                except Exception:
                    pass

                price_candidates = find_price_candidates(body_text)[:50]

                browser.close()

                results.append({
                    "offset": offset,
                    "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat(),
                    "check_in_day": check_in_day,
                    "check_out_day": check_out_day,
                    "clicked_in": clicked_in,
                    "clicked_out": clicked_out,
                    "apply_disabled_before_click": apply_disabled,
                    "apply_html": apply_html[:600],
                    "apply_clicked": apply_clicked,
                    "price_button_clicked": price_button_clicked,
                    "arrival_value": arrival_value,
                    "departure_value": departure_value,
                    "object_price": object_price,
                    "before_cells": before_cells[:80],
                    "after_first_click_cells": after_first_click_cells[:80],
                    "after_second_click_cells": after_second_click_cells[:80],
                    "after_apply_text": after_apply_text[:2000],
                    "price_candidates": price_candidates,
                    "text_after": body_text[:3000]
                })

        return {
            "ok": True,
            "results": results
        }

    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error_text": str(e),
            "error_repr": repr(e)
        }


@app.post("/debug-network")
def debug_network(request: ParseRequest):
    try:
        today = date.today()
        offset = request.offsets[0] if request.offsets else 7

        check_in = today + timedelta(days=offset)
        nights = max(int(request.nights or 2), 2)
        check_out = check_in + timedelta(days=nights)

        check_in_day = str(check_in.day)
        check_out_day = str(check_out.day)

        captured_requests = []
        captured_responses = []

        keywords = [
            "price",
            "booking",
            "calendar",
            "order",
            "availability",
            "object",
            "cost",
            "calc",
            "bron",
            "date"
        ]

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

            context = browser.new_context(
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )

            page = context.new_page()

            def request_handler(req):
                url = req.url
                lower_url = url.lower()

                if any(k in lower_url for k in keywords):
                    post_data = None
                    try:
                        post_data = req.post_data
                    except Exception:
                        pass

                    captured_requests.append({
                        "method": req.method,
                        "url": url,
                        "resource_type": req.resource_type,
                        "post_data": post_data[:1000] if post_data else None
                    })

            def response_handler(resp):
                url = resp.url
                lower_url = url.lower()

                if any(k in lower_url for k in keywords):
                    captured_responses.append({
                        "status": resp.status,
                        "url": url
                    })

            page.on("request", request_handler)
            page.on("response", response_handler)

            page.goto(request.url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            try:
                page.locator("#modal-cookies-accept").click(timeout=2000)
                page.wait_for_timeout(1000)
            except Exception:
                pass

            # Открываем календарь
            try:
                page.locator(".js-booking-calendar-field").first.click(timeout=10000)
                page.wait_for_timeout(3000)
            except Exception:
                pass

            # Клик заезда
            try:
                cells = page.locator("td.available:not(.disabled)")
                for i in range(cells.count()):
                    cell = cells.nth(i)
                    text = cell.inner_text(timeout=1000).strip()
                    if text == check_in_day:
                        cell.click(timeout=3000)
                        page.wait_for_timeout(3000)
                        break
            except Exception:
                pass

            # Клик выезда
            try:
                cells = page.locator("td.available:not(.disabled)")
                for i in range(cells.count()):
                    cell = cells.nth(i)
                    text = cell.inner_text(timeout=1000).strip()
                    if text == check_out_day:
                        cell.click(timeout=3000)
                        page.wait_for_timeout(5000)
                        break
            except Exception:
                pass

            # Пробуем кнопку Цена и доступность
            try:
                page.locator(".js-show-booking-price").click(timeout=5000)
                page.wait_for_timeout(8000)
            except Exception:
                pass

            body_text = page.locator("body").inner_text(timeout=10000)

            browser.close()

            return {
                "ok": True,
                "check_in": check_in.isoformat(),
                "check_out": check_out.isoformat(),
                "captured_requests_count": len(captured_requests),
                "captured_responses_count": len(captured_responses),
                "captured_requests": captured_requests[:80],
                "captured_responses": captured_responses[:80],
                "text_after": body_text[:2000]
            }

    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "error_text": str(e),
            "error_repr": repr(e)
        }


def calculate_price_by_calendar(url, offset, guests, nights):
    today = date.today()

    check_in = today + timedelta(days=int(offset))
    check_out = check_in + timedelta(days=int(nights))

    check_in_day = str(check_in.day)
    check_out_day = str(check_out.day)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        try:
            page.locator("#modal-cookies-accept").click(timeout=2000)
            page.wait_for_timeout(1000)
        except Exception:
            pass

        # Открываем календарь
        page.locator(".js-booking-calendar-field").first.click(timeout=10000)
        page.wait_for_timeout(3000)

        clicked_in = False
        clicked_out = False

        # Кликаем дату заезда
        cells = page.locator("td.available:not(.disabled)")
        for i in range(cells.count()):
            cell = cells.nth(i)
            try:
                text = cell.inner_text(timeout=1000).strip()
                if text == check_in_day:
                    cell.click(timeout=3000)
                    clicked_in = True
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                pass

        # Кликаем дату выезда
        cells = page.locator("td.available:not(.disabled)")
        for i in range(cells.count()):
            cell = cells.nth(i)
            try:
                text = cell.inner_text(timeout=1000).strip()
                if text == check_out_day:
                    cell.click(timeout=3000)
                    clicked_out = True
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                pass

        # Очень важное ожидание: после второго клика Суточно перерисовывает блок бронирования
        page.wait_for_timeout(10000)

        body_text = page.locator("body").inner_text(timeout=15000)

        # Иногда цена появляется не сразу, поэтому делаем еще 2 попытки
        total_price = extract_calculated_price(body_text, nights)
        price_candidates = find_price_candidates(body_text)[:30]

        for _ in range(2):
            if total_price:
                break
            page.wait_for_timeout(5000)
            body_text = page.locator("body").inner_text(timeout=15000)
            total_price = extract_calculated_price(body_text, nights)
            price_candidates = find_price_candidates(body_text)[:30]

        prepaid_price = extract_prepaid_price(body_text)

        price_per_night = None
        if total_price:
           price_per_night = round(total_price / nights)

        error_reason = ""

        if not clicked_in:
           error_reason = f"Не удалось выбрать дату заезда {check_in.isoformat()}"
        elif not clicked_out:
           error_reason = f"Не удалось выбрать дату выезда {check_out.isoformat()}"
        elif not total_price:
           found_prices = []
           for item in price_candidates[:5]:
             found_prices.append(str(item.get("price", "")))

           found_prices_text = ", ".join([p for p in found_prices if p])

           if found_prices_text:
             error_reason = (
              f"Расчетная цена не найдена. Найдены другие суммы: {found_prices_text}. "
              f"Возможно, это депозит/предоплата, объект занят или минимум ночей больше {nights}."
              )
           else:
              error_reason = (
              f"Цена не найдена после выбора дат {check_in.isoformat()}–{check_out.isoformat()}. "
              f"Возможно, объект занят, даты недоступны или требуется другой минимум ночей."
             )

        title = ""
        try:
            title = page.locator("h1").first.inner_text(timeout=3000)
        except Exception:
            try:
                title = page.title()
            except Exception:
                title = ""

        browser.close()

        return {
            "offset": offset,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "nights": nights,
            "clicked_in": clicked_in,
            "clicked_out": clicked_out,
            "total_price": total_price,
            "price_per_night": price_per_night,
            "prepaid_price": prepaid_price,
            "available": total_price is not None,
            "title": title,
            "price_candidates": price_candidates,
            "text_after": body_text[:2500],
            "error": error_reason
        }


# ==========================================================================
# АПГРЕЙД (занятость по дням) — читаем календарь ОДНИМ визитом на объект.
# Не трогает расчёт цен выше. Основа сравнительной таблицы «ты vs конкуренты».
# ==========================================================================

# Русские названия месяцев (полные и короткие) -> номер месяца.
RU_MONTHS = {
    "январь": 1, "янв": 1, "января": 1,
    "февраль": 2, "фев": 2, "февраля": 2,
    "март": 3, "мар": 3, "марта": 3,
    "апрель": 4, "апр": 4, "апреля": 4,
    "май": 5, "мая": 5,
    "июнь": 6, "июн": 6, "июня": 6,
    "июль": 7, "июл": 7, "июля": 7,
    "август": 8, "авг": 8, "августа": 8,
    "сентябрь": 9, "сен": 9, "сент": 9, "сентября": 9,
    "октябрь": 10, "окт": 10, "октября": 10,
    "ноябрь": 11, "ноя": 11, "нояб": 11, "ноября": 11,
    "декабрь": 12, "дек": 12, "декабря": 12,
}


def parse_month_caption(caption):
    """Из подписи календаря ('Ноябрь 2026' / 'ноя 2026') -> (год, месяц)."""
    if not caption:
        return None

    low = caption.strip().lower()

    year_match = re.search(r"(20\d{2})", low)
    year = int(year_match.group(1)) if year_match else None

    month = None
    for name, num in RU_MONTHS.items():
        if re.search(r"\b" + re.escape(name), low):
            month = num
            break

    if month is None:
        return None

    return (year, month)


# JS, который снимает все видимые ячейки-дни календаря bootstrap-daterangepicker.
# Возвращает по каждой ячейке: подпись месяца, число, список классов.
CALENDAR_SNAPSHOT_JS = r"""
() => {
  const out = [];
  const tables = document.querySelectorAll(
    ".daterangepicker table.table-condensed, .daterangepicker table, table.table-condensed"
  );
  tables.forEach((tb) => {
    let cap = "";
    const th = tb.querySelector("th.month");
    if (th) cap = th.textContent.trim();
    tb.querySelectorAll("td").forEach((td) => {
      const t = (td.textContent || "").trim();
      if (!/^\d{1,2}$/.test(t)) return;
      out.push({
        cap: cap,
        day: parseInt(t, 10),
        cls: td.className || "",
        dataDate: td.getAttribute("data-date") || td.getAttribute("data-day") || ""
      });
    });
  });
  return out;
}
"""


def classify_cell(cls):
    """
    По классам ячейки календаря Суточно:
      'off'       — день чужого месяца (пропускаем);
      'res_first' — день ЗАЕЗДА чужой брони (reserved-first-time);
      'res_last'  — день ВЫЕЗДА чужой брони (reserved-last-time);
      'res_mid'   — иной день внутри брони (reserved…);
      'blocked'   — закрыт/занят без available;
      'free'      — свободен к брони.
    Диагностическая стадия: res_* различаем, чтобы сверить с RC, какие из них
    реально = занятая ночь.
    """
    c = " " + (cls or "") + " "
    if " off " in c:
        return "off"
    if "reserved-first-time" in c:
        return "res_first"
    if "reserved-last-time" in c:
        return "res_last"
    if "reserved" in c:
        return "res_mid"
    if " available " in c and " disabled " not in c:
        return "free"
    return "blocked"


def read_calendar_occupancy(url, months=3):
    """
    Открывает календарь объекта и считывает занятость по дням на ближайшие
    `months` месячных экрана. Один визит в браузер (без перебора дат).
    Возвращает {"ok", "occupancy": [{"date","status"}...], "raw_sample", "error"}.
    status: 'free' (свободно к брони) / 'busy' (занято или закрыто).
    """
    today = date.today()
    occ = {}            # date -> status (free/busy), берём первое не-off значение
    cls_hist = {}       # класс ячейки (внутри месяца) -> счётчик (диагностика)
    raw_sample = []
    error = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)

            try:
                page.locator("#modal-cookies-accept").click(timeout=2000)
                page.wait_for_timeout(800)
            except Exception:
                pass

            # Открываем календарь: до 3 попыток — скролл к виджету, клик, ждём ячейки.
            opened = False
            for attempt in range(3):
                try:
                    field = page.locator(".js-booking-calendar-field").first
                    try:
                        field.scroll_into_view_if_needed(timeout=4000)
                    except Exception:
                        pass
                    field.wait_for(state="visible", timeout=10000)
                    field.click(timeout=8000)
                    page.wait_for_timeout(2500)
                    page.wait_for_selector(
                        ".daterangepicker td, table.table-condensed td",
                        timeout=9000
                    )
                    opened = True
                    error = ""
                    break
                except Exception as e:
                    error = "Открытие календаря (попытка %d/3): %s" % (attempt + 1, repr(e))
                    page.wait_for_timeout(3500)

            if not opened:
                browser.close()
                return {
                    "ok": False,
                    "occupancy": [],
                    "class_hist": [],
                    "raw_sample": [],
                    "error": error or "Календарь не открылся"
                }

            for step in range(max(1, int(months))):
                try:
                    cells = page.evaluate(CALENDAR_SNAPSHOT_JS)
                except Exception as e:
                    cells = []
                    error = "evaluate: " + repr(e)

                # первые ячейки сохраняем «как есть» для диагностики структуры
                if len(raw_sample) < 20:
                    for c in cells[:20]:
                        raw_sample.append({
                            "cap": c.get("cap", ""),
                            "day": c.get("day"),
                            "cls": c.get("cls", "")
                        })

                for c in cells:
                    status = classify_cell(c.get("cls", ""))
                    if status == "off":
                        continue

                    # диагностика: какими классами помечены дни ВНУТРИ месяца
                    cls_key = (c.get("cls", "") or "").strip()
                    cls_hist[cls_key] = cls_hist.get(cls_key, 0) + 1

                    ym = parse_month_caption(c.get("cap", ""))
                    if not ym or not ym[0] or not ym[1]:
                        continue

                    try:
                        d = date(ym[0], ym[1], int(c.get("day")))
                    except Exception:
                        continue

                    if d < today:
                        continue

                    iso = d.isoformat()
                    # free имеет приоритет не нужен — просто фиксируем первое значение
                    if iso not in occ:
                        occ[iso] = status

                # переход к следующему экрану месяцев
                clicked = False
                for sel in [".daterangepicker th.next", "th.next.available", "th.next", ".daterangepicker .next"]:
                    try:
                        loc = page.locator(sel).first
                        loc.click(timeout=2000)
                        page.wait_for_timeout(1200)
                        clicked = True
                        break
                    except Exception:
                        pass
                if not clicked:
                    break

        except Exception as e:
            error = (error + " | " if error else "") + repr(e)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    # ВОССТАНОВЛЕНИЕ ЗАНЯТОСТИ ПО ГРАНИЦАМ (подтверждено сверкой с RC на Фокина 31):
    #  - свободная ночь = день 'free' ИЛИ 'res_first' (день выезда — ночь уже свободна);
    #  - занятая ночь  = 'res_last' (день заезда — ночь занята), 'res_mid'/'blocked',
    #    А ТАКЖЕ дни, которых НЕТ среди доступных (глухую середину брони Суточно прячет).
    avail_dates = [
        date.fromisoformat(k) for k, v in occ.items()
        if v in ("free", "res_first", "res_last")
    ]
    end_d = max(avail_dates) if avail_dates else today

    markers = []  # диагностика: дни с явной меткой (res_first/res_last/blocked)
    occupancy = []
    d = today
    while d <= end_d:
        cat = occ.get(d.isoformat())
        if cat and cat != "free":
            markers.append(d.isoformat() + ":" + cat)
        is_free = cat in ("free", "res_first")
        occupancy.append({"date": d.isoformat(), "status": "free" if is_free else "busy"})
        d += timedelta(days=1)

    free_count = sum(1 for x in occupancy if x["status"] == "free")
    busy_count = len(occupancy) - free_count

    # словарь классов (по убыванию частоты) — для проверки, как помечены занятые дни
    class_hist = sorted(cls_hist.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "ok": len(occupancy) > 0,
        "days_total": len(occupancy),
        "free": free_count,
        "busy": busy_count,
        "occupancy": occupancy,
        "markers": markers,
        "class_hist": class_hist,
        "raw_sample": raw_sample,
        "error": error
    }


@app.post("/parse-occupancy")
def parse_occupancy(request: ParseRequest):
    """Тестовый endpoint: занятость по дням для одного объекта."""
    try:
        return read_calendar_occupancy(request.url, months=3)
    except Exception as e:
        return {
            "ok": False,
            "occupancy": [],
            "raw_sample": [],
            "error": repr(e)
        }


@app.post("/parse-sutochno")
def parse_sutochno(request: ParseRequest):
    nights = max(int(request.nights or 2), 2)

    title = ""
    rating = ""
    reviews = ""
    max_guests = ""
    rooms = ""
    area = ""
    floor = ""
    superhost = False

    # Сначала читаем общие данные карточки
    try:
        data = open_page_and_get_data(request.url)
        text = data["body_text"]

        title = data["title"]
        rating = extract_rating(text)
        reviews = extract_reviews(text)
        max_guests = extract_guests(text)
        rooms = extract_rooms(text)
        area = extract_area(text)
        floor = extract_floor(text)
        superhost = extract_superhost(text)

    except Exception:
        pass

    results = []

    for offset in request.offsets:
        try:
            price_data = calculate_price_by_calendar(
                url=request.url,
                offset=int(offset),
                guests=int(request.guests or 4),
                nights=nights
            )

            results.append({
             "offset": offset,
             "check_in": price_data["check_in"],
             "check_out": price_data["check_out"],
             "nights": nights,
             "total_price": price_data["total_price"],
             "price": price_data["price_per_night"],
             "available": price_data["available"],
             "error": price_data["error"]
            })

        except Exception as e:
            check_in = date.today() + timedelta(days=int(offset))
            check_out = check_in + timedelta(days=nights)

            results.append({
                "offset": offset,
                "check_in": check_in.isoformat(),
                "check_out": check_out.isoformat(),
                "nights": nights,
                "total_price": None,
                "price": None,
                "available": False,
                "error": str(e)
            })

        time.sleep(2)

    return {
        "id": request.id,
        "url": request.url,
        "guests": request.guests,
        "nights": nights,
        "title": title,
        "address": "",
        "rooms": rooms,
        "max_guests": max_guests,
        "area": area,
        "floor": floor,
        "superhost": superhost,
        "rating": rating,
        "reviews": reviews,
        "results": results
    }
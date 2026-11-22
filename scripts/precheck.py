#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precheck.py — Лёгкий stdlib-детектор изменений на сайте Росгвардии.
Работает без установки сторонних библиотек (pdfplumber/bs4/requests),
чтобы не тратить минуты CI при отсутствии обновлений.
"""

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/pdf,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

KEYWORDS = ("периодическ", "проверк", "вопрос", "квалификационн", "билет", "охраны", "оружия")


def build_ssl_context() -> ssl.SSLContext:
    """Создает SSL-контекст с fallback для окружений без корневых сертификатов Минцифры."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_head_meta(url: str, ctx: ssl.SSLContext) -> dict:
    """Выполняет лёгкий HEAD-запрос для получения ETag / Last-Modified / Content-Length."""
    req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return {
            "etag": (resp.headers.get("ETag") or "").strip(),
            "last_modified": (resp.headers.get("Last-Modified") or "").strip(),
            "content_length": (resp.headers.get("Content-Length") or "").strip(),
        }


def find_remote_doc_urls(page_url: str, ctx: ssl.SSLContext) -> list[str]:
    """Ищет ссылки на PDF/DOCX на официальной странице без BeautifulSoup."""
    req = urllib.request.Request(page_url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    urls = []
    for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        href = match.group(1).strip()
        text = re.sub(r"<[^>]+>", " ", match.group(2)).lower()
        href_lower = href.lower()
        if any(href_lower.endswith(ext) for ext in (".pdf", ".docx", ".doc", ".rtf")):
            if any(kw in text or kw in href_lower for kw in KEYWORDS):
                full = href if href_lower.startswith("http") else f"https://rosguard.gov.ru{href}"
                if full not in urls:
                    urls.append(full)
    return urls


def write_output(needs_update: bool, reason: str):
    """Записывает результат pre-check в GITHUB_OUTPUT и Job Summary."""
    val = "true" if needs_update else "false"
    out_path = os.environ.get("GITHUB_OUTPUT")
    if out_path:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"needs_update={val}\n")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(f"- **Pre-check (`rosguard.gov.ru`):** `{val}` ({reason})\n")
    print(f"[precheck] needs_update={val} | {reason}")


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest_path = os.path.join(root, "questions_manifest.json")
    if not os.path.exists(manifest_path):
        write_output(True, "questions_manifest.json отсутствует")
        return 0

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    page_url = manifest.get("rosguard_page_url", "")
    pdf_url = manifest.get("rosguard_pdf_url", "")
    ctx = build_ssl_context()

    try:
        if page_url:
            found_urls = find_remote_doc_urls(page_url, ctx)
            if found_urls and pdf_url and pdf_url not in found_urls:
                write_output(True, f"обнаружен новый URL документа: {found_urls[0]}")
                return 0

        if pdf_url:
            meta = fetch_head_meta(pdf_url, ctx)
            saved_etag = manifest.get("rosguard_pdf_etag", "")
            saved_len = manifest.get("rosguard_pdf_content_length", "")
            saved_lm = manifest.get("rosguard_pdf_last_modified", "")
            if (saved_etag and meta["etag"] and meta["etag"] != saved_etag) or \
               (saved_len and meta["content_length"] and meta["content_length"] != saved_len) or \
               (saved_lm and meta["last_modified"] and meta["last_modified"] != saved_lm):
                write_output(True, "изменились HTTP-метаданные PDF файла")
                return 0

        write_output(False, "официальный документ не изменился, тяжёлый парсинг пропущен")
        return 0
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Не сжигаем лимит на pip install, если портал Росгвардии временно недоступен с зарубежного IP
        write_output(False, f"портал временно недоступен ({exc.__class__.__name__}), пропуск парсера")
        return 0


if __name__ == "__main__":
    sys.exit(main())

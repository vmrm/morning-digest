"""
Юнит-тесты на чистую логику (без сети).
Запуск: APPLE_ID=x APPLE_APP_PASSWORD=x TELEGRAM_TOKEN=x TELEGRAM_CHAT_ID=x python -m pytest
Сетевые функции (CalDAV, Telegram) здесь не тестируются.
"""

import os

# Модуль читает секреты на импорте — подставляем заглушки.
os.environ.setdefault("APPLE_ID", "test@icloud.com")
os.environ.setdefault("APPLE_APP_PASSWORD", "test-pass")
os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")

import digest  # noqa: E402


def test_md_escape_covers_all_special_chars():
    assert digest.md_escape("a_b*c[d]") == "a\\_b\\*c\\[d\\]"
    assert digest.md_escape("1.2.3") == "1\\.2\\.3"
    # Раньше эти символы ломали отправку — теперь экранируются.
    assert digest.md_escape("C# = a+b") == "C\\# \\= a\\+b"


def test_md_escape_leaves_plain_text():
    assert digest.md_escape("Привет мир") == "Привет мир"


def test_format_message_empty():
    msg = digest.format_message([])
    assert "Встреч сегодня нет" in msg


def test_format_message_escapes_tricky_summary():
    events = [(None, "10:00", "Sync w/ team (Q3) #plan")]
    msg = digest.format_message(events)
    # Спецсимволы должны быть экранированы, отправка не должна падать.
    assert "\\(Q3\\)" in msg
    assert "\\#plan" in msg


def test_split_for_telegram_short_message_one_chunk():
    assert digest._split_for_telegram("hello") == ["hello"]


def test_split_for_telegram_splits_long_message():
    text = "\n".join(f"line {i}" for i in range(2000))
    chunks = digest._split_for_telegram(text, limit=500)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    # Ничего не потеряли.
    assert "\n".join(chunks) == text

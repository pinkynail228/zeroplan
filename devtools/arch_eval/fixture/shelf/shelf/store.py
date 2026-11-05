"""Books are one JSON list in $SHELF_HOME/books.json (default ~/.shelf)."""
import json
import os
from pathlib import Path


def home():
    return Path(os.environ.get("SHELF_HOME") or Path.home() / ".shelf")


def load():
    path = home() / "books.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save(books):
    path = home() / "books.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(books, ensure_ascii=False, indent=1), encoding="utf-8")


def add(title, author=""):
    books = load()
    book = {"id": max((b["id"] for b in books), default=0) + 1, "title": title, "author": author, "read": False}
    books.append(book)
    save(books)
    return book


def mark_read(book_id):
    books = load()
    for book in books:
        if book["id"] == book_id:
            book["read"] = True
            save(books)
            return book
    raise KeyError(book_id)

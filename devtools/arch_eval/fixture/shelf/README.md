# shelf

A reading list in your terminal: add books, mark them read, keep a queue.

## Run locally

    make dev      # the web view on http://localhost:8731
    make test     # python3 -m unittest discover -s tests

Books live in `~/.shelf/books.json` (one JSON list). Set `SHELF_HOME` to keep them elsewhere.

## Commands

    python3 -m shelf add "Dune" --author "Frank Herbert"
    python3 -m shelf list
    python3 -m shelf done 1
    python3 -m shelf queue

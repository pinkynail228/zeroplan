# The pivot (October 2026)

Until September shelf was a hosted service (shelf.cloud) with accounts and sync. We shut the hosted service down
on 2026-10-12: there is no production any more, and everything runs on the owner's machine.

- `server/` is the old hosted API. It is kept for reference only; nothing imports it and it is not deployed.
- The local web view (`shelf/web.py`) replaced the hosted site. It serves read-only pages on port 8731.
- Sync and accounts are gone. Import from Goodreads was planned for the hosted service and never built.

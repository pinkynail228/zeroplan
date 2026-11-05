# Legacy development harness — inactive

This directory is retained temporarily for graph diagnostics and tests that still reference it.

Do not use `run.sh` for product development, dogfood, or release qualification. It bypasses the product conversation and planning path and builds a synthetic proposal.

The active project rules are in `AGENTS.md`, `docs/PRODUCT_CONTRACT.md`, and `docs/DEVELOPMENT.md`. New work must use the product Application Service and its headless frontend when available. Remove the legacy runner together with its remaining consumers; do not extend it.

# Spherical Robot Fixture Boundary

This fixture is split by trust and runtime permission:

- `seed/`: deterministic user-owned demo input that may be loaded idempotently.
- `external/`: deterministic provider/search/crawl responses that may be loaded only when the user explicitly selects fixture mode.
- `expected/`: verification-only outputs; runtime application code must never read this directory.
- `negative/`: verification-only malformed outputs; runtime application code must never read this directory.

Gate 0 establishes the directory boundary only. Canonical fixture payloads are added by their owning implementation tasks and must validate against generated contracts before use.
"""One module per strategic lens, one lane owner per module.

Coordinator-owned package init. Kept import-free so parallel lens lanes never
conflict here; explicit registration lives in :mod:`app.strategic_lenses.registry`.
"""

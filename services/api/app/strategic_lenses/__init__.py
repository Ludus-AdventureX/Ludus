"""Strategic lens runtime behaviors.

Coordinator-owned package init. Deliberately free of lens imports, side effects
and registries: five lens lanes develop in parallel and explicit assembly happens
only in :mod:`app.strategic_lenses.registry`. Do not add per-lens imports here.
"""

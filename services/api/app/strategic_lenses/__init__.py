"""Strategic lens runtime behaviors.

One module per lens, one lane owner per module. Keep this package init free of
lens imports and registries so parallel lens lanes do not conflict on merge.
"""

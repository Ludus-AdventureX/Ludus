"""Per-lens implementation modules.

Each lane registers its own module here. This ``__init__`` intentionally does
NOT import the individual lens modules: the Ways Coordinator's registry wiring
decides what gets registered, and keeping this file import-free avoids merge
conflicts between the five independent lens lanes.
"""

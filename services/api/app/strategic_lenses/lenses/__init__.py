"""Strategic-lens specialist implementations.

Each lens lane contributes exactly one module here implementing the
``LensImplementation`` seam owned by the Ways Coordinator
(``app.agents.lenses``). Lanes never edit each other's modules, the shared
seam, canonical schema, manifest, or migrations.
"""

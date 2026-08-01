"""PROTOTYPE A2A remote-agent surface (PandaAI track) — not a product contract.

Everything under ``app.a2a`` is additive and hard-gated by ``A2A_ENABLED``:
when the flag is unset/false, ``mount_a2a`` mounts nothing and the deployed
service is byte-for-byte identical to the pre-A2A behavior (the switch-back
guarantee). No module here writes to the database, touches tenancy/auth, or
mutates any frozen contract surface; the five-lens engine is consumed strictly
through its stable seams (``LensRegistry``, ``WorkerRunner``, ``ModelProvider``).
"""

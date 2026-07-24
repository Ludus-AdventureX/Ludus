"""Strategic-lens specialist implementations.

Each lane conversation (7-11) owns exactly one ``LensImplementation`` under
``strategic_lenses/lenses/``. This package holds no shared runtime, schema,
manifest or persistence logic - those belong to the Ways Coordinator seam in
``app.agents`` and to contract_lead / case_api_data. The Ways Coordinator wires
the implementations into the shared ``LensRegistry`` during assembly.
"""

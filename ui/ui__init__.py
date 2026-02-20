"""
ui/__init__.py
==============
Paquete de componentes de presentación Streamlit del Validador de Crudos.

IMPORTANTE: Este paquete requiere Streamlit. No importar desde tests unitarios
de core/ ni desde código que se ejecute sin entorno Streamlit.
"""
from ui.styling import (
    render_all_results,
    render_pairing_feedback,
    render_summary,
    render_crudo_detail,
    render_threshold_editor,
    SEMAFORO_CSS,
)

__all__ = [
    "render_all_results",
    "render_pairing_feedback",
    "render_summary",
    "render_crudo_detail",
    "render_threshold_editor",
    "SEMAFORO_CSS",
]

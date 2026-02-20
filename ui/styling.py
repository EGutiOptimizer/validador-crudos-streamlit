"""
ui/styling.py
=============
Componentes de presentación para Streamlit.

IMPORTANTE: Este módulo SÍ puede importar streamlit.
No debe contener lógica de negocio (clasificación, cálculo de errores).
Solo renderiza datos ya procesados por core/.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.models import ValidationResult  # ThresholdConfig no se usa aquí: eliminado
from core.validator_core import SEMAFORO_LABELS

# ---------------------------------------------------------------------------
# Colores CSS para semáforos (sin usar pd.Styler — compatible Cloud)
# ---------------------------------------------------------------------------

SEMAFORO_CSS = {
    "verde": "background-color: #92D050; color: #1a3a1a; font-weight: bold;",
    "amarillo": "background-color: #FFEB9C; color: #5a4a00; font-weight: bold;",
    "rojo": "background-color: #FF6666; color: #3a0000; font-weight: bold;",
}


# ---------------------------------------------------------------------------
# Helpers de color (internos)
# ---------------------------------------------------------------------------

def _color_for_semaforo_label(val: str) -> str:
    """Devuelve CSS para una celda dado su label con emoji (ej. '🟢 OK').

    Compatible con pandas >= 2.1 (usa .map en lugar del deprecado .applymap).
    """
    for key, label in SEMAFORO_LABELS.items():
        if val == label:
            return SEMAFORO_CSS.get(key, "")
    return ""


def _color_for_semaforo_key(val: str) -> str:
    """Devuelve CSS para una celda dado su valor clave (ej. 'verde').

    Usado en render_summary donde la columna estado_global contiene labels con emoji.
    """
    for key, label in SEMAFORO_LABELS.items():
        if val == label:
            return SEMAFORO_CSS.get(key, "")
    return ""


# ---------------------------------------------------------------------------
# Componentes de feedback
# ---------------------------------------------------------------------------

def render_pairing_feedback(result: ValidationResult) -> None:
    """Muestra alertas sobre archivos no emparejados."""
    if not result.unpaired_isa and not result.unpaired_rams:
        st.success(f"✅ Todos los archivos emparejados correctamente ({result.total_pairs} pares).")
        return

    if result.paired_names:
        st.info(f"ℹ️ {result.total_pairs} par(es) procesado(s) correctamente.")

    if result.unpaired_isa:
        st.warning(
            f"⚠️ **{len(result.unpaired_isa)} archivo(s) ISA sin par RAMS:**\n\n"
            + "\n".join(f"- `{f}`" for f in result.unpaired_isa)
        )

    if result.unpaired_rams:
        st.warning(
            f"⚠️ **{len(result.unpaired_rams)} archivo(s) RAMS sin par ISA:**\n\n"
            + "\n".join(f"- `{f}`" for f in result.unpaired_rams)
        )


# ---------------------------------------------------------------------------
# Componentes de resultados
# ---------------------------------------------------------------------------

def render_summary(result: ValidationResult) -> None:
    """Renderiza la tabla resumen global por crudo con semáforo de estado."""
    if result.summary.empty:
        st.info("Sin datos de resumen disponibles.")
        return

    st.subheader("📊 Resumen Global por Crudo")

    display = result.summary.copy()
    # Mapear valor crudo ('verde') → label con emoji ('🟢 OK')
    display["estado_global"] = display["estado_global"].map(
        lambda v: SEMAFORO_LABELS.get(v, v)
    )

    # .map() es el nombre correcto en pandas >= 2.1 (applymap fue eliminado en 3.x)
    styled = display.style.map(_color_for_semaforo_key, subset=["estado_global"])
    st.dataframe(styled, use_container_width=True)


def render_crudo_detail(
    canon_name: str,
    error_df: pd.DataFrame,
    semaforo_df: pd.DataFrame,
) -> None:
    """Renderiza el detalle de errores y semáforo para un crudo específico."""
    with st.expander(f"🛢️ Crudo: **{canon_name}**", expanded=False):
        tab_semaforo, tab_errores = st.tabs(["🚦 Semáforo", "📐 Errores Absolutos"])

        with tab_semaforo:
            _render_semaforo_table(semaforo_df)

        with tab_errores:
            _render_error_table(error_df)


def _render_semaforo_table(semaforo_df: pd.DataFrame) -> None:
    """Renderiza tabla de semáforo con colores de celda."""
    prop_cols = list(semaforo_df.columns)

    display = semaforo_df.copy().reset_index()
    # reset_index() convierte el índice (que tiene nombre = key_col) en columna;
    # no hace falta rename porque el nombre ya es correcto.

    # Mapear claves internas a labels con emoji solo en columnas de propiedades
    for col in prop_cols:
        display[col] = display[col].map(lambda v: SEMAFORO_LABELS.get(v, v))

    # .map() compatible con pandas >= 2.1
    styled = display.style.map(_color_for_semaforo_label, subset=prop_cols)
    st.dataframe(styled, use_container_width=True)


def _render_error_table(error_df: pd.DataFrame) -> None:
    """Renderiza tabla de errores absolutos con gradiente de color."""
    display = error_df.copy().reset_index()
    # reset_index() convierte el índice en columna con su nombre original

    numeric_cols = [c for c in error_df.columns if pd.api.types.is_numeric_dtype(error_df[c])]

    if numeric_cols:
        styled = display.style.background_gradient(
            subset=numeric_cols, cmap="RdYlGn_r", vmin=0
        ).format({c: "{:.4f}" for c in numeric_cols}, na_rep="N/D")
    else:
        styled = display.style

    st.dataframe(styled, use_container_width=True)


def render_all_results(result: ValidationResult) -> None:
    """Renderiza todos los resultados de validación."""
    render_pairing_feedback(result)

    if not result.has_results:
        st.error("❌ No se pudo procesar ningún par de archivos.")
        return

    render_summary(result)

    st.subheader("🔍 Detalle por Crudo")
    for name in result.paired_names:
        render_crudo_detail(
            name,
            result.error_matrices[name],
            result.semaforo_matrices[name],
        )


# ---------------------------------------------------------------------------
# Sidebar helpers
# ---------------------------------------------------------------------------

def render_threshold_editor(
    prop_cols: list[str],
    default_green: float,
    default_yellow: float,
) -> dict[str, tuple[float, float]]:
    """Renderiza editor de umbrales por propiedad en el sidebar.

    Args:
        prop_cols: Lista de propiedades disponibles (puede estar vacía al inicio).
        default_green: Umbral verde global por defecto.
        default_yellow: Umbral amarillo global por defecto.

    Returns:
        Mapa propiedad → (umbral_verde, umbral_amarillo).
    """
    thresholds: dict[str, tuple[float, float]] = {}

    if not prop_cols:
        st.caption("Los umbrales por propiedad aparecerán tras subir archivos ISA.")
        return thresholds

    use_custom = st.checkbox(
        "Personalizar umbrales por propiedad",
        value=False,
        help="Si está desactivado, se aplican los umbrales globales a todas las propiedades.",
    )

    if not use_custom:
        return thresholds

    st.caption("Define umbrales Verde / Amarillo por propiedad:")
    for prop in prop_cols:
        col1, col2 = st.columns(2)
        with col1:
            g = st.number_input(
                f"{prop} — Verde ≤",
                min_value=0.0,
                max_value=1000.0,
                value=default_green,
                step=0.1,
                key=f"thresh_green_{prop}",
            )
        with col2:
            y = st.number_input(
                f"{prop} — Amarillo ≤",
                min_value=0.0,
                max_value=1000.0,
                value=default_yellow,
                step=0.1,
                key=f"thresh_yellow_{prop}",
            )
        if g >= y:
            st.error(f"⚠️ '{prop}': umbral verde ({g}) debe ser menor que amarillo ({y}).")
        else:
            thresholds[prop] = (g, y)

    return thresholds

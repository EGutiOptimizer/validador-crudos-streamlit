"""
ui/styling.py
=============
Componentes de presentación para Streamlit.

Renderiza resultados del pipeline con paridad visual al MVP:
  - Tabla Resumen (Propiedad × crudos) con colores de semáforo y fila GLOBAL
  - Detalle por crudo: tabla completa con columnas Semaforo + cortes numéricos
  - Colores idénticos al Excel del MVP: C6EFCE / FFEB9C / FFC7CE / E7E6E6
  - Botones de descarga CSV explícitos (no dependen del icono nativo del dataframe)

Sin lógica de negocio — solo presentación de datos ya calculados por core/.
"""
from __future__ import annotations

import io
import re

import pandas as pd
import streamlit as st

from core.models import ValidationResult

# ---------------------------------------------------------------------------
# Paleta de colores (idéntica al MVP)
# ---------------------------------------------------------------------------

SEMAFORO_CSS: dict[str, str] = {
    "VERDE":    "background-color: #C6EFCE; color: #1a3a1a; font-weight: bold;",
    "AMARILLO": "background-color: #FFEB9C; color: #5a4a00; font-weight: bold;",
    "ROJO":     "background-color: #FFC7CE; color: #3a0000; font-weight: bold;",
    "NA":       "background-color: #E7E6E6; color: #555555; font-weight: bold;",
}

SEMAFORO_EMOJI: dict[str, str] = {
    "VERDE":    "🟢 VERDE",
    "AMARILLO": "🟡 AMARILLO",
    "ROJO":     "🔴 ROJO",
    "NA":       "⚪ N/A",
    "":         "",
}


def _cell_sem_css(val: str) -> str:
    return SEMAFORO_CSS.get(str(val).strip().upper(), "")


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serializa un DataFrame a CSV en UTF-8 con BOM (compatible con Excel español)."""
    return df.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig").encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Feedback de emparejamiento
# ---------------------------------------------------------------------------

def render_pairing_feedback(result: ValidationResult) -> None:
    """Muestra estado de emparejamiento de archivos."""
    if not result.unpaired_isa and not result.unpaired_rams:
        st.success(
            f"✅ Todos los archivos emparejados correctamente "
            f"({result.total_pairs} par{'es' if result.total_pairs != 1 else ''})."
        )
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
# Tabla Resumen (idéntica a la hoja Resumen del MVP)
# ---------------------------------------------------------------------------

def render_summary(result: ValidationResult) -> None:
    """
    Renderiza la tabla Resumen con:
      - Fila GLOBAL al inicio (semáforo del crudo completo)
      - Una fila por propiedad × columna por crudo
      - Colores de celda idénticos al Excel del MVP
    """
    if result.summary.empty:
        st.info("Sin datos de resumen disponibles.")
        return

    st.subheader("📊 Resumen Global (Propiedad × Crudo)")

    display = result.summary.copy()
    crudo_cols = [c for c in display.columns if c != "Propiedad"]

    # Mapear a etiquetas con emoji solo para visualización
    for col in crudo_cols:
        display[col] = display[col].map(
            lambda v: SEMAFORO_EMOJI.get(str(v).strip().upper(), str(v))
        )

    def _style_cell(val: str) -> str:
        for key, label in SEMAFORO_EMOJI.items():
            if val == label:
                return SEMAFORO_CSS.get(key, "")
        return ""

    if crudo_cols:
        styled = display.style.applymap(_style_cell, subset=crudo_cols)
    else:
        styled = display.style

    st.dataframe(styled, use_container_width=True, height=min(600, 38 * len(display) + 40))

    # Botón de descarga CSV del resumen (usa el DataFrame original sin emojis)
    st.download_button(
        label="⬇️ Descargar Resumen CSV",
        data=_df_to_csv_bytes(result.summary),
        file_name="resumen_validacion.csv",
        mime="text/csv",
        key="dl_resumen_csv",
    )


# ---------------------------------------------------------------------------
# Detalle por crudo
# ---------------------------------------------------------------------------

def render_crudo_detail(
    crude_name: str,
    df_out: pd.DataFrame,
    cortes_visibles: list[str],
) -> None:
    """
    Renderiza el detalle de un crudo con:
    Tab 1: Semáforo — columnas Propiedad | Semaforo | Corte_peor | Error_peor | Umbral_peor
    Tab 2: Errores  — columnas Propiedad | [cortes numéricos con colores]
    Botones de descarga CSV debajo de cada tab.
    """
    # Nombre seguro para usar en claves Streamlit y nombres de archivo
    safe_name = re.sub(r"[^A-Za-z0-9_\-]", "_", crude_name)

    with st.expander(f"🛢️ Crudo: **{crude_name}**", expanded=False):
        tab_sem, tab_err = st.tabs(["🚦 Semáforo", "📐 Errores Absolutos"])

        with tab_sem:
            _render_semaforo_tab(df_out)
            # CSV de la vista semáforo (columnas de clasificación)
            sem_cols = ["Propiedad", "Semaforo", "Corte_peor", "Error_peor", "Umbral_peor"]
            sem_cols_present = [c for c in sem_cols if c in df_out.columns]
            st.download_button(
                label="⬇️ Descargar Semáforo CSV",
                data=_df_to_csv_bytes(df_out[sem_cols_present]),
                file_name=f"semaforo_{safe_name}.csv",
                mime="text/csv",
                key=f"dl_sem_{safe_name}",
            )

        with tab_err:
            _render_errores_tab(df_out, cortes_visibles)
            # CSV de errores absolutos completo (todas las columnas)
            st.download_button(
                label="⬇️ Descargar Errores CSV",
                data=_df_to_csv_bytes(df_out),
                file_name=f"errores_{safe_name}.csv",
                mime="text/csv",
                key=f"dl_err_{safe_name}",
            )


def _render_semaforo_tab(df_out: pd.DataFrame) -> None:
    """Muestra columnas de clasificación con colores de semáforo."""
    sem_cols = ["Propiedad", "Semaforo", "Corte_peor", "Error_peor", "Umbral_peor"]
    sem_cols_present = [c for c in sem_cols if c in df_out.columns]
    display = df_out[sem_cols_present].copy()

    # Mapear a etiquetas con emoji
    if "Semaforo" in display.columns:
        display["Semaforo"] = display["Semaforo"].map(
            lambda v: SEMAFORO_EMOJI.get(str(v).strip().upper(), str(v))
        )

    def _style(val: str) -> str:
        for key, label in SEMAFORO_EMOJI.items():
            if val == label:
                return SEMAFORO_CSS.get(key, "")
        return ""

    numeric_fmt_cols = [c for c in ["Error_peor", "Umbral_peor"] if c in display.columns]

    styled = display.style.applymap(_style, subset=["Semaforo"]) if "Semaforo" in display.columns else display.style
    if numeric_fmt_cols:
        styled = styled.format({c: "{:.4f}" for c in numeric_fmt_cols}, na_rep="N/D")

    st.dataframe(styled, use_container_width=True)


def _render_errores_tab(df_out: pd.DataFrame, cortes_visibles: list[str]) -> None:
    """Muestra errores numéricos por corte. Colorea celdas según el semáforo de cada fila."""
    corte_cols_present = [c for c in cortes_visibles if c in df_out.columns]
    prop_col = ["Propiedad"] if "Propiedad" in df_out.columns else []
    display_cols = prop_col + corte_cols_present
    display = df_out[display_cols].copy()

    if not corte_cols_present:
        st.dataframe(display, use_container_width=True)
        return

    # Colorea cada celda numérica según el semáforo de esa fila (sin matplotlib)
    sem_col = df_out["Semaforo"] if "Semaforo" in df_out.columns else None

    def _color_row(row: pd.Series) -> list[str]:
        """Asigna color de fondo a cada celda según el semáforo de la fila."""
        # Localizar el semáforo de esta fila por índice posicional
        sem = ""
        if sem_col is not None:
            try:
                sem = str(sem_col.iloc[row.name] if hasattr(row, "name") else "").upper()
            except Exception:
                sem = ""
        bg = SEMAFORO_CSS.get(sem, "")
        # Solo colorear columnas de corte, dejar Propiedad sin color
        styles = []
        for col in row.index:
            if col in corte_cols_present and pd.notna(row[col]):
                styles.append(bg)
            else:
                styles.append("")
        return styles

    styled = (
        display.reset_index(drop=True)
        .style
        .apply(_color_row, axis=1)
        .format({c: "{:.4f}" for c in corte_cols_present}, na_rep="N/D")
    )

    st.dataframe(styled, use_container_width=True)


# ---------------------------------------------------------------------------
# Render completo
# ---------------------------------------------------------------------------

def render_all_results(result: ValidationResult) -> None:
    """Renderiza todos los resultados de validación."""
    render_pairing_feedback(result)

    if not result.has_results:
        st.error("❌ No se pudo procesar ningún par de archivos.")
        return

    render_summary(result)

    st.subheader("🔍 Detalle por Crudo")
    for name in result.paired_names:
        df_out = result.crudo_dataframes.get(name, pd.DataFrame())
        cortes = result.cortes_visibles.get(name, [])
        render_crudo_detail(name, df_out, cortes)

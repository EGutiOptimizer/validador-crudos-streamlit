"""
app.py — Validador de Crudos RAMS vs ISA
==========================================
Entrypoint principal para Streamlit Cloud.

Lógica de semáforo por corte (v2):
  - error < REPRO              → 🟢 VERDE
  - REPRO ≤ error < ADMISIBLE → 🟡 AMARILLO
  - error ≥ ADMISIBLE          → 🔴 ROJO

Flujo:
  1. Sidebar: Matriz de Umbrales + ISA + RAMS + parámetros globales.
  2. Botón "Ejecutar Validación".
  3. Área principal: resumen + detalle por crudo.
  4. Descarga de Excel con formato condicional.
"""
from __future__ import annotations

import logging
import io
from typing import Any

import streamlit as st

from core.validator_core import (
    run_validation,
    build_excel,
    DEFAULT_PCT_OK_AMARILLO,
    DEFAULT_PCT_ROJO_ROJO,
)
from ui.styling import render_all_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Validador de Crudos RAMS/ISA",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Validador de crudos RAMS vs ISA. © Todos los derechos reservados.",
        "Report a bug": None,
        "Get help": None,
    },
)


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "matriz_file":  None,
        "isa_files":    [],
        "rams_files":   [],
        "result":       None,
        "excel_bytes":  None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_sidebar():
    """Renderiza el sidebar y devuelve los parámetros de ejecución."""
    with st.sidebar:
        st.title("🛢️ Validador de Crudos")
        st.caption("RAMS vs ISA — Análisis de errores por propiedad y corte")
        st.divider()

        # --- 1. Matriz de umbrales ---
        st.header("📋 Matriz de Umbrales")
        matriz_uploaded = st.file_uploader(
            "Selecciona la Matriz de Umbrales",
            type=["xlsx", "xls", "csv"],
            accept_multiple_files=False,
            help=(
                "Archivo Excel con columna 'Propiedad', columna 'Tipo' "
                "(Reproductibilidad / Admisible) y una columna por corte."
            ),
            key="uploader_matriz",
        )
        if matriz_uploaded:
            st.session_state.matriz_file = matriz_uploaded
        if st.session_state.matriz_file:
            st.success(f"✅ Matriz cargada: `{st.session_state.matriz_file.name}`")

        sheet_hint = st.text_input(
            "Hoja de la matriz (vacío = primera)",
            value="",
            help="Nombre o índice (0-based) de la hoja. Vacío = primera hoja.",
            key="sheet_hint",
        )
        sheet_hint = sheet_hint.strip() if sheet_hint.strip() else None

        st.divider()

        # --- 2. Archivos ISA ---
        st.header("📂 Archivos ISA")
        isa_uploaded = st.file_uploader(
            "Selecciona archivos ISA",
            type=["xlsx", "xls", "csv"],
            accept_multiple_files=True,
            key="uploader_isa",
        )
        if isa_uploaded:
            st.session_state.isa_files = isa_uploaded
        if st.session_state.isa_files:
            st.success(f"✅ {len(st.session_state.isa_files)} archivo(s) ISA cargado(s)")

        # --- 3. Archivos RAMS ---
        st.header("📂 Archivos RAMS")
        rams_uploaded = st.file_uploader(
            "Selecciona archivos RAMS",
            type=["xlsx", "xls", "csv"],
            accept_multiple_files=True,
            key="uploader_rams",
        )
        if rams_uploaded:
            st.session_state.rams_files = rams_uploaded
        if st.session_state.rams_files:
            st.success(f"✅ {len(st.session_state.rams_files)} archivo(s) RAMS cargado(s)")

        st.divider()

        # --- 4. Parámetros de agregación global ---
        st.header("⚙️ Parámetros Globales")
        st.caption(
            "El semáforo por corte usa directamente los umbrales **REPRO** y **ADMISIBLE** "
            "de la matriz. Estos parámetros controlan la agregación a nivel de propiedad y crudo."
        )

        col1, col2 = st.columns(2)
        with col1:
            pct_ok_amarillo = st.number_input(
                "% mín. VERDE global",
                min_value=0.0,
                max_value=1.0,
                value=float(st.secrets.get("defaults", {}).get("pct_ok_amarillo", DEFAULT_PCT_OK_AMARILLO)),
                step=0.05,
                format="%.2f",
                help="Si ≥ X% de cortes son VERDE, la propiedad/crudo es VERDE (ej. 0.90 = 90%).",
            )
        with col2:
            pct_rojo_rojo = st.number_input(
                "% máx. ROJO global",
                min_value=0.0,
                max_value=1.0,
                value=float(st.secrets.get("defaults", {}).get("pct_rojo_rojo", DEFAULT_PCT_ROJO_ROJO)),
                step=0.05,
                format="%.2f",
                help="Si > X% de cortes son ROJO, la propiedad/crudo es ROJO (ej. 0.30 = 30%).",
            )

        st.divider()
        st.caption("© Todos los derechos reservados")

    return (
        st.session_state.matriz_file,
        st.session_state.isa_files,
        st.session_state.rams_files,
        sheet_hint,
        pct_ok_amarillo,
        pct_rojo_rojo,
    )


def main() -> None:
    _init_state()

    (
        matriz_file,
        isa_files_raw,
        rams_files_raw,
        sheet_hint,
        pct_ok_amarillo,
        pct_rojo_rojo,
    ) = render_sidebar()

    st.title("🛢️ Validador de Crudos RAMS vs ISA")
    st.caption(
        "Sube la **Matriz de Umbrales** (con columnas Reproductibilidad y Admisible), "
        "los archivos **ISA** y **RAMS** en el sidebar, y pulsa **Ejecutar Validación**."
    )

    # Leyenda de semáforo
    with st.expander("ℹ️ Criterios de clasificación por corte", expanded=False):
        st.markdown(
            "| Color | Criterio |\n"
            "|---|---|\n"
            "| 🟢 **VERDE** | error < REPRO |\n"
            "| 🟡 **AMARILLO** | REPRO ≤ error < ADMISIBLE |\n"
            "| 🔴 **ROJO** | error ≥ ADMISIBLE |\n"
            "| ⚪ **N/A** | Sin umbral definido en la matriz |\n\n"
            "La clasificación **global de propiedad** agrega los semáforos de todos "
            "sus cortes usando los parámetros de la barra lateral."
        )

    all_ready = bool(matriz_file and isa_files_raw and rams_files_raw)
    missing = []
    if not matriz_file:
        missing.append("Matriz de Umbrales")
    if not isa_files_raw:
        missing.append("archivos ISA")
    if not rams_files_raw:
        missing.append("archivos RAMS")

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_btn = st.button(
            "▶ Ejecutar Validación",
            type="primary",
            disabled=not all_ready,
            use_container_width=True,
        )
    with col_info:
        if not all_ready:
            st.info(f"📌 Faltan en el sidebar: **{', '.join(missing)}**.")

    st.divider()

    if run_btn:
        if not (0.0 <= pct_ok_amarillo <= 1.0 and 0.0 <= pct_rojo_rojo <= 1.0):
            st.error("❌ Los porcentajes deben estar en [0, 1].")
            st.stop()

        progress = st.progress(0, text="⏳ Iniciando validación...")

        try:
            matriz_file.seek(0)
            matriz_bytes = io.BytesIO(matriz_file.read())

            isa_dict: dict[str, io.BytesIO] = {}
            for f in isa_files_raw:
                f.seek(0)
                isa_dict[f.name] = io.BytesIO(f.read())

            rams_dict: dict[str, io.BytesIO] = {}
            for f in rams_files_raw:
                f.seek(0)
                rams_dict[f.name] = io.BytesIO(f.read())

            progress.progress(20, text="⏳ Leyendo matriz de umbrales (REPRO + ADMISIBLE)...")

            result = run_validation(
                isa_files=isa_dict,
                rams_files=rams_dict,
                matriz_file=matriz_bytes,
                matriz_filename=matriz_file.name,
                pct_ok_amarillo=pct_ok_amarillo,
                pct_rojo_rojo=pct_rojo_rojo,
                sheet_hint=sheet_hint,
            )

            progress.progress(80, text="⏳ Generando Excel...")
            st.session_state.result = result
            st.session_state.excel_bytes = build_excel(result) if result.has_results else None
            progress.progress(100, text="✅ Validación completada.")
            logger.info(
                "Completado: %d pares, %d ISA sin par, %d RAMS sin par",
                result.total_pairs,
                len(result.unpaired_isa),
                len(result.unpaired_rams),
            )

        except ValueError as e:
            st.error(f"❌ Error de configuración o datos: {e}")
            logger.warning("ValueError: %s", e)
            progress.empty()
            st.stop()
        except Exception as e:
            st.error(f"❌ Error inesperado: {e}")
            logger.exception("Error inesperado en run_validation")
            progress.empty()
            st.stop()

    if st.session_state.result is not None:
        render_all_results(st.session_state.result)

        if st.session_state.excel_bytes:
            st.divider()
            st.download_button(
                label="📥 Descargar Informe Excel",
                data=st.session_state.excel_bytes,
                file_name="validacion_crudos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=False,
            )


if __name__ == "__main__":
    main()

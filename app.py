"""
app.py — Validador de Crudos RAMS vs ISA
==========================================
Entrypoint principal para Streamlit Cloud.

PARIDAD TOTAL con validador_crudos.py (MVP CLI):
  - Requiere archivo de matriz de umbrales (igual que el MVP)
  - Mismos parámetros: tolerancia, tol_pesados, pct_ok_amarillo, pct_rojo_rojo
  - Misma estructura de resultados: hoja Resumen + hojas por crudo
  - Excel de salida idéntico al MVP en estructura y colores

Flujo:
  1. Sidebar: subida de Matriz de Umbrales + ISA + RAMS, parámetros.
  2. Botón único "Ejecutar Validación".
  3. Área principal: resultados (resumen + detalle por crudo).
  4. Descarga de Excel con formato condicional (idéntico al MVP).
"""
from __future__ import annotations

import logging
import io
from typing import Any

import streamlit as st

from core.validator_core import (
    run_validation,
    build_excel,
    read_file,
    DEFAULT_TOL,
    DEFAULT_TOL_PESADOS,
    DEFAULT_PCT_OK_AMARILLO,
    DEFAULT_PCT_ROJO_ROJO,
)
from ui.styling import render_all_results

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Inicialización de session_state
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults: dict[str, Any] = {
        "matriz_file": None,
        "isa_files": [],
        "rams_files": [],
        "result": None,
        "excel_bytes": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar():
    """Renderiza el sidebar y devuelve todos los parámetros de ejecución."""
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
                "Archivo Excel con los umbrales de reproductibilidad. "
                "Debe tener columna 'Propiedad', columna 'Tipo' y una columna por corte."
            ),
            key="uploader_matriz",
        )
        if matriz_uploaded:
            st.session_state.matriz_file = matriz_uploaded
        if st.session_state.matriz_file:
            st.success(f"✅ Matriz cargada: `{st.session_state.matriz_file.name}`")

        # Hoja de la matriz (opcional)
        sheet_hint = st.text_input(
            "Hoja de la matriz (vacío = primera)",
            value="",
            help="Nombre o índice (0-based) de la hoja del Excel de umbrales. Déjalo vacío para usar la primera hoja.",
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
            help="Archivos de referencia ISA. Soporta .xlsx, .xls, .csv",
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
            help="Archivos de predicciones RAMS a validar.",
            key="uploader_rams",
        )
        if rams_uploaded:
            st.session_state.rams_files = rams_uploaded
        if st.session_state.rams_files:
            st.success(f"✅ {len(st.session_state.rams_files)} archivo(s) RAMS cargado(s)")

        st.divider()

        # --- 4. Parámetros (idénticos al MVP) ---
        st.header("⚙️ Parámetros de Validación")

        col1, col2 = st.columns(2)
        with col1:
            tol = st.number_input(
                "Tolerancia estándar",
                min_value=0.0,
                max_value=10.0,
                value=float(st.secrets.get("defaults", {}).get("tolerancia", DEFAULT_TOL)),
                step=0.01,
                format="%.2f",
                help=(
                    "Margen adicional sobre el umbral para clasificar como AMARILLO "
                    "en cortes normales (ej. 0.10 = 10%)."
                ),
            )
        with col2:
            tol_pesados = st.number_input(
                "Tolerancia cortes pesados",
                min_value=0.0,
                max_value=10.0,
                value=float(st.secrets.get("defaults", {}).get("tol_pesados", DEFAULT_TOL_PESADOS)),
                step=0.05,
                format="%.2f",
                help=(
                    "Tolerancia ampliada para cortes ≥ 299°C o C6-C10 "
                    "(ej. 0.60 = 60%)."
                ),
            )

        col3, col4 = st.columns(2)
        with col3:
            pct_ok_amarillo = st.number_input(
                "% mín. VERDE global",
                min_value=0.0,
                max_value=1.0,
                value=float(st.secrets.get("defaults", {}).get("pct_ok_amarillo", DEFAULT_PCT_OK_AMARILLO)),
                step=0.05,
                format="%.2f",
                help=(
                    "Si el X% o más de propiedades son verdes, "
                    "el crudo es VERDE globalmente (ej. 0.90 = 90%)."
                ),
            )
        with col4:
            pct_rojo_rojo = st.number_input(
                "% máx. ROJO global",
                min_value=0.0,
                max_value=1.0,
                value=float(st.secrets.get("defaults", {}).get("pct_rojo_rojo", DEFAULT_PCT_ROJO_ROJO)),
                step=0.05,
                format="%.2f",
                help=(
                    "Si más del X% de propiedades son rojas, "
                    "el crudo es ROJO globalmente (ej. 0.30 = 30%)."
                ),
            )

        st.divider()
        st.caption("© Todos los derechos reservados")

    return (
        st.session_state.matriz_file,
        st.session_state.isa_files,
        st.session_state.rams_files,
        sheet_hint,
        tol,
        tol_pesados,
        pct_ok_amarillo,
        pct_rojo_rojo,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _init_state()

    (
        matriz_file,
        isa_files_raw,
        rams_files_raw,
        sheet_hint,
        tol,
        tol_pesados,
        pct_ok_amarillo,
        pct_rojo_rojo,
    ) = render_sidebar()

    # --- Área principal ---
    st.title("🛢️ Validador de Crudos RAMS vs ISA")
    st.caption(
        "Sube la **Matriz de Umbrales**, los archivos **ISA** y **RAMS** en el sidebar, "
        "configura los parámetros y pulsa **Ejecutar Validación**."
    )

    # Botón y estado de requisitos
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
            help="Requiere Matriz de Umbrales + al menos 1 archivo ISA y 1 RAMS.",
        )
    with col_info:
        if not all_ready:
            st.info(f"📌 Faltan en el sidebar: **{', '.join(missing)}**.")

    st.divider()

    # --- Ejecución ---
    if run_btn:
        # Validación de parámetros en UI (no lógica de negocio)
        if tol < 0 or tol_pesados < 0:
            st.error("❌ Las tolerancias no pueden ser negativas.")
            st.stop()
        if not (0.0 <= pct_ok_amarillo <= 1.0 and 0.0 <= pct_rojo_rojo <= 1.0):
            st.error("❌ Los porcentajes deben estar en [0, 1].")
            st.stop()

        progress = st.progress(0, text="⏳ Iniciando validación...")

        try:
            # Convertir UploadedFiles a BytesIO
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

            progress.progress(20, text="⏳ Leyendo matriz de umbrales...")

            result = run_validation(
                isa_files=isa_dict,
                rams_files=rams_dict,
                matriz_file=matriz_bytes,
                matriz_filename=matriz_file.name,
                tol=tol,
                tol_pesados=tol_pesados,
                pct_ok_amarillo=pct_ok_amarillo,
                pct_rojo_rojo=pct_rojo_rojo,
                sheet_hint=sheet_hint,
            )

            progress.progress(80, text="⏳ Generando Excel...")

            st.session_state.result = result

            if result.has_results:
                st.session_state.excel_bytes = build_excel(result)
            else:
                st.session_state.excel_bytes = None

            progress.progress(100, text="✅ Validación completada.")
            logger.info(
                "Validación completada: %d pares, %d ISA sin par, %d RAMS sin par",
                result.total_pairs,
                len(result.unpaired_isa),
                len(result.unpaired_rams),
            )

        except ValueError as e:
            st.error(f"❌ Error de configuración o datos: {e}")
            logger.warning("ValueError en validación: %s", e)
            progress.empty()
            st.stop()
        except Exception as e:
            st.error(f"❌ Error inesperado: {e}")
            logger.exception("Error inesperado en run_validation")
            progress.empty()
            st.stop()

    # --- Renderizar resultados (persistentes vía session_state) ---
    if st.session_state.result is not None:
        result = st.session_state.result
        render_all_results(result)

        if st.session_state.excel_bytes:
            st.divider()
            st.download_button(
                label="📥 Descargar Informe Excel",
                data=st.session_state.excel_bytes,
                file_name="validacion_crudos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=False,
                help=(
                    "Excel idéntico al generado por el validador CLI: "
                    "Hoja Resumen + hoja por crudo con formato condicional de color."
                ),
            )


if __name__ == "__main__":
    main()

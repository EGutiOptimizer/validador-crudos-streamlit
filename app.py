"""
app.py — Validador de Crudos RAMS vs ISA
==========================================
Entrypoint principal para Streamlit Cloud.

Flujo:
  1. Sidebar: subida de archivos ISA + RAMS, configuración de parámetros.
  2. Botón único "Ejecutar Validación".
  3. Área principal: resultados (resumen + detalle por crudo).
  4. Descarga de Excel con formato condicional.
"""
from __future__ import annotations

import logging
import io
from typing import Any

import streamlit as st

from core.models import ThresholdConfig
from core.validator_core import run_validation, build_excel, read_file
from ui.styling import render_all_results, render_threshold_editor

# ---------------------------------------------------------------------------
# Configuración de logging (no verbose, no exponer datos sensibles)
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
# Helpers de session_state
# ---------------------------------------------------------------------------

def _init_state() -> None:
    """Inicializa claves de session_state si no existen."""
    defaults: dict[str, Any] = {
        "isa_files": [],
        "rams_files": [],
        "result": None,
        "excel_bytes": None,
        "prop_cols_detected": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _read_uploaded_files(uploaded_list) -> dict[str, io.BytesIO]:
    """Convierte lista de UploadedFile a dict nombre → BytesIO."""
    result = {}
    for f in uploaded_list:
        try:
            result[f.name] = io.BytesIO(f.read())
        except Exception as e:
            st.error(f"❌ Error leyendo '{f.name}': {e}")
    return result


@st.cache_data(show_spinner=False)
def _cached_detect_prop_cols(file_bytes: bytes, filename: str) -> list[str]:
    """Detecta columnas numéricas de un archivo ISA (cacheado por contenido)."""
    try:
        buf = io.BytesIO(file_bytes)
        df = read_file(buf, filename)
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        return numeric_cols
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> tuple[dict, dict, str, ThresholdConfig]:
    """Renderiza el sidebar completo y devuelve configuración de ejecución."""
    with st.sidebar:
        st.title("🛢️ Validador de Crudos")
        st.caption("RAMS vs ISA — Análisis de errores por propiedad y corte")
        st.divider()

        # --- Subida de archivos ---
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
            # Detectar propiedades del primer ISA
            first = isa_uploaded[0]
            first.seek(0)
            cols = _cached_detect_prop_cols(first.read(), first.name)
            first.seek(0)
            st.session_state.prop_cols_detected = cols

        if st.session_state.isa_files:
            st.success(f"✅ {len(st.session_state.isa_files)} archivo(s) ISA cargado(s)")

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

        # --- Parámetros ---
        st.header("⚙️ Parámetros")

        key_col = st.text_input(
            "Columna clave (cortes)",
            value=st.secrets.get("defaults", {}).get("key_col", "corte"),
            help="Nombre exacto de la columna que identifica los cortes en los archivos.",
        )

        st.subheader("Umbrales globales")
        col1, col2 = st.columns(2)
        with col1:
            default_green = st.number_input(
                "🟢 Verde ≤",
                min_value=0.0,
                max_value=1000.0,
                value=float(st.secrets.get("defaults", {}).get("umbral_verde", 1.0)),
                step=0.1,
                help="Error máximo para clasificar como verde (OK).",
            )
        with col2:
            default_yellow = st.number_input(
                "🟡 Amarillo ≤",
                min_value=0.0,
                max_value=1000.0,
                value=float(st.secrets.get("defaults", {}).get("umbral_amarillo", 3.0)),
                step=0.1,
                help="Error máximo para clasificar como amarillo (Revisar). Por encima → rojo.",
            )

        if default_green >= default_yellow:
            st.error("⚠️ El umbral verde debe ser menor que el amarillo.")

        st.divider()

        # --- Umbrales por propiedad ---
        st.header("🔧 Umbrales por propiedad")
        prop_thresholds = render_threshold_editor(
            prop_cols=st.session_state.prop_cols_detected,
            default_green=default_green,
            default_yellow=default_yellow,
        )

        st.divider()
        st.caption("© Todos los derechos reservados")

    config = ThresholdConfig(
        thresholds=prop_thresholds,
        default_green=default_green,
        default_yellow=default_yellow,
    )

    return (
        st.session_state.isa_files,
        st.session_state.rams_files,
        key_col,
        config,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _init_state()

    isa_files_raw, rams_files_raw, key_col, config = render_sidebar()

    # --- Área principal ---
    st.title("🛢️ Validador de Crudos RAMS vs ISA")
    st.caption(
        "Sube los archivos ISA y RAMS en el sidebar, configura los umbrales "
        "y pulsa **Ejecutar Validación** para obtener el análisis completo."
    )

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_btn = st.button(
            "▶ Ejecutar Validación",
            type="primary",
            disabled=(not isa_files_raw or not rams_files_raw),
            use_container_width=True,
            help="Requiere al menos 1 archivo ISA y 1 RAMS cargados.",
        )

    with col_info:
        if not isa_files_raw or not rams_files_raw:
            st.info("📌 Carga archivos ISA y RAMS en el sidebar para activar la validación.")

    st.divider()

    # --- Ejecución ---
    if run_btn:
        # Validar umbral antes de ejecutar
        if config.default_green >= config.default_yellow:
            st.error("❌ Corrige los umbrales antes de ejecutar: verde debe ser < amarillo.")
            st.stop()

        if not key_col.strip():
            st.error("❌ Especifica el nombre de la columna clave (cortes).")
            st.stop()

        with st.spinner("⏳ Procesando validación..."):
            try:
                # Convertir UploadedFiles a BytesIO (sin escribir a disco)
                isa_dict: dict[str, io.BytesIO] = {}
                for f in isa_files_raw:
                    f.seek(0)
                    isa_dict[f.name] = io.BytesIO(f.read())

                rams_dict: dict[str, io.BytesIO] = {}
                for f in rams_files_raw:
                    f.seek(0)
                    rams_dict[f.name] = io.BytesIO(f.read())

                result = run_validation(
                    isa_files=isa_dict,
                    rams_files=rams_dict,
                    key_col=key_col.strip(),
                    config=config,
                )

                st.session_state.result = result

                if result.has_results:
                    excel_bytes = build_excel(result, config)
                    st.session_state.excel_bytes = excel_bytes
                else:
                    st.session_state.excel_bytes = None

                logger.info(
                    "Validación completada: %d pares, %d ISA sin par, %d RAMS sin par",
                    result.total_pairs,
                    len(result.unpaired_isa),
                    len(result.unpaired_rams),
                )

            except ValueError as e:
                st.error(f"❌ Error de configuración: {e}")
                logger.warning("ValueError en validación: %s", e)
                st.stop()
            except Exception as e:
                st.error(f"❌ Error inesperado durante la validación: {e}")
                logger.exception("Error inesperado en run_validation")
                st.stop()

    # --- Renderizar resultados (persisten entre reruns gracias a session_state) ---
    if st.session_state.result is not None:
        result = st.session_state.result
        render_all_results(result)

        # Botón de descarga Excel
        if st.session_state.excel_bytes:
            st.divider()
            st.download_button(
                label="📥 Descargar Informe Excel",
                data=st.session_state.excel_bytes,
                file_name="validacion_crudos.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=False,
                help="Descarga el informe completo con errores, semáforos y resumen por crudo.",
            )


if __name__ == "__main__":
    main()

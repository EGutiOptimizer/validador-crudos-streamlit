# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd

from core.validator_core import (
    run_validation_in_memory,
    leer_tabla_errores_filelike,
)
from ui.styling import style_matrix, map_emoji, style_semaforo_column

st.set_page_config(
    page_title="Validador de Crudos (RAMS / ISA)",
    layout="wide",
    page_icon="🛢️",
)

st.title("🛢️ Validador de Crudos (RAMS / ISA)")
st.caption("Comparación RAMS vs ISA, semáforos por propiedad y resumen global — versión Streamlit")

with st.sidebar:
    st.header("⚙️ Configuración")
    st.write("1) Sube la **matriz de umbrales** y, si procede, elige la hoja.")
    matriz_file = st.file_uploader("Matriz de umbrales (Excel)", type=["xlsx", "xls"])
    matriz_sheet = st.text_input("Nombre de hoja (opcional). Déjalo vacío para la primera hoja.", value="")
    st.write("---")
    st.write("2) Sube **ISA** y **RAMS** (varios archivos). Los emparejaremos por nombre base.")
    isa_files = st.file_uploader("Archivos ISA", accept_multiple_files=True, type=["xlsx","xls","csv"])
    rams_files = st.file_uploader("Archivos RAMS", accept_multiple_files=True, type=["xlsx","xls","csv"])

    st.write("---")
    st.write("3) Reglas de evaluación")
    tolerancia = st.number_input("Tolerancia estándar (ej. 0.10 → +10%)", min_value=0.0, max_value=2.0, value=0.10, step=0.01)
    tol_pesados = st.number_input("Tolerancia cortes pesados (≥299 o C6..C10)", min_value=0.0, max_value=2.0, value=0.60, step=0.05)
    pct_ok_amarillo = st.slider("Umbral VERDE global (≥ este % de verdes)", min_value=0.0, max_value=1.0, value=0.90, step=0.05)
    pct_rojo_rojo = st.slider("Umbral ROJO global (> este % de rojos)", min_value=0.0, max_value=1.0, value=0.30, step=0.05)

    st.write("---")
    validar = st.button("✅ Validar ahora", use_container_width=True)

def _files_to_tuples(uploaded_list):
    return [(f.name, f.getvalue()) for f in (uploaded_list or [])]

if validar:
    if not matriz_file:
        st.error("Sube primero la **matriz de umbrales**.")
        st.stop()
    if not isa_files or not rams_files:
        st.error("Sube al menos un archivo **ISA** y otro **RAMS**.")
        st.stop()

    try:
        with st.spinner("Procesando..."):
            df_resumen, resumen_dict, hojas, orden_props, excel_bytes = run_validation_in_memory(
                matriz_bytes=matriz_file.getvalue(),
                matriz_name=matriz_file.name,
                matriz_sheet=matriz_sheet or None,
                isa_files=_files_to_tuples(isa_files),
                rams_files=_files_to_tuples(rams_files),
                tolerancia=tolerancia,
                pct_ok_amarillo=pct_ok_amarillo,
                pct_rojo_rojo=pct_rojo_rojo,
                tol_pesados=tol_pesados,
            )

        st.success("¡Validación completada!")

        # Resumen (propiedades × crudos)
        st.subheader("📊 Resumen (Propiedad × Crudo)")
        if not df_resumen.empty:
            # Añadimos emojis para una lectura rápida
            df_show = df_resumen.copy()
            for c in df_show.columns:
                if c == "Propiedad":
                    continue
                df_show[c] = df_show[c].apply(lambda v: f"{map_emoji(v)} {v}" if v else "")
            st.dataframe(df_show, use_container_width=True)
            # (Opcional) si prefieres color de fondo: st.dataframe(style_matrix(df_resumen), use_container_width=True)

        # Hojas por crudo (detalles)
        st.subheader("📑 Detalle por crudo")
        for hoja_name, df_out in hojas:
            with st.expander(f"Crudo: {hoja_name}", expanded=False):
                if df_out.empty:
                    st.info("Sin filas para este crudo.")
                    continue
                df_show = df_out.copy()
                # Emojis en Semaforo
                df_show["Semaforo"] = df_show["Semaforo"].apply(lambda v: f"{map_emoji(v)} {v}" if v else "")
                st.dataframe(df_show, use_container_width=True)

        st.download_button(
            label="💾 Descargar Excel con formato",
            data=excel_bytes,
            file_name="Validacion.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    except Exception as e:
        st.exception(e)
else:
    st.info("Configura y sube los archivos a la izquierda, y pulsa **Validar ahora**.")
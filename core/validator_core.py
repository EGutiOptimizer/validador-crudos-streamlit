"""
validator_core.py
=================
Lógica de negocio pura para validación de crudos RAMS vs ISA.

Sin dependencias de Streamlit — 100% testeable en aislamiento.
Todas las funciones reciben y devuelven tipos estándar (str, float, DataFrame).
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
from typing import IO

import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core.models import ValidationResult, ThresholdConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

SEMAFORO_COLORS = {
    "verde": "FF92D050",      # verde Excel
    "amarillo": "FFFFEB9C",   # amarillo Excel
    "rojo": "FFFF0000",       # rojo Excel
}

SEMAFORO_LABELS = {
    "verde": "🟢 OK",
    "amarillo": "🟡 Revisar",
    "rojo": "🔴 Fuera de rango",
}

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


# ---------------------------------------------------------------------------
# 1. Canonización de nombres
# ---------------------------------------------------------------------------

def canonize_name(name: str) -> str:
    """Normaliza el nombre de un archivo para emparejamiento ISA↔RAMS tolerante.

    Elimina extensión, prefijos/sufijos ISA/RAMS, acentos, espacios
    y caracteres no alfanuméricos. Convierte a minúsculas.

    Args:
        name: Nombre de archivo original (con o sin extensión).

    Returns:
        Cadena normalizada para comparación.

    Examples:
        >>> canonize_name("ISA_Crudo_Maya.xlsx")
        'crudomaya'
        >>> canonize_name("RAMS-Crudo_Maya.xlsx")
        'crudomaya'
        >>> canonize_name("Crudo Máya_ISA.xlsx")
        'crudomaya'
    """
    # 1. Eliminar extensión
    name = re.sub(r"\.[^.]+$", "", name)
    # 2. Normalizar Unicode → eliminar acentos
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    # 3. Eliminar prefijos ISA/RAMS (inicio)
    name = re.sub(r"^(isa|rams)[_\-\s]*", "", name, flags=re.IGNORECASE)
    # 4. Eliminar sufijos ISA/RAMS (final)
    name = re.sub(r"[_\-\s]*(isa|rams)$", "", name, flags=re.IGNORECASE)
    # 5. Solo alfanumérico, minúsculas
    name = re.sub(r"[^a-z0-9]", "", name.lower())
    return name


def pair_files(
    isa_names: list[str],
    rams_names: list[str],
) -> tuple[dict[str, tuple[str, str]], list[str], list[str]]:
    """Empareja archivos ISA y RAMS por nombre canónico.

    Args:
        isa_names: Lista de nombres de archivos ISA.
        rams_names: Lista de nombres de archivos RAMS.

    Returns:
        Tupla de:
        - paired: Mapa nombre_canónico → (nombre_isa, nombre_rams)
        - unpaired_isa: Archivos ISA sin par
        - unpaired_rams: Archivos RAMS sin par
    """
    isa_canon = {canonize_name(n): n for n in isa_names}
    rams_canon = {canonize_name(n): n for n in rams_names}

    paired: dict[str, tuple[str, str]] = {}
    for canon, isa_file in isa_canon.items():
        if canon in rams_canon:
            paired[canon] = (isa_file, rams_canon[canon])
            logger.debug("Par encontrado: '%s' → ISA=%s, RAMS=%s", canon, isa_file, rams_canon[canon])

    unpaired_isa = [isa_canon[c] for c in isa_canon if c not in rams_canon]
    unpaired_rams = [rams_canon[c] for c in rams_canon if c not in isa_canon]

    if unpaired_isa:
        logger.warning("Archivos ISA sin par RAMS: %s", unpaired_isa)
    if unpaired_rams:
        logger.warning("Archivos RAMS sin par ISA: %s", unpaired_rams)

    return paired, unpaired_isa, unpaired_rams


# ---------------------------------------------------------------------------
# 2. Lectura de archivos
# ---------------------------------------------------------------------------

def read_file(file_obj: IO[bytes], filename: str) -> pd.DataFrame:
    """Lee un archivo subido (BytesIO o UploadedFile) a DataFrame.

    Soporta .xlsx, .xls, .csv (con coma decimal y auto-detección de separador).
    No escribe nada a disco — opera completamente en memoria.

    Args:
        file_obj: Objeto con interfaz de archivo (read() / seek()).
        filename: Nombre original del archivo (para detectar extensión).

    Returns:
        DataFrame con el contenido del archivo.

    Raises:
        ValueError: Si la extensión no es soportada o el archivo no se puede leer.
    """
    ext = _get_extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Formato no soportado: '{ext}'. "
            f"Use: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    data = io.BytesIO(file_obj.read() if hasattr(file_obj, "read") else file_obj)

    if ext == ".csv":
        return _read_csv(data, filename)
    elif ext == ".xlsx":
        return _read_excel(data, filename, engine="openpyxl")
    elif ext == ".xls":
        return _read_excel(data, filename, engine="xlrd")
    else:  # pragma: no cover
        raise ValueError(f"Extensión inesperada: {ext}")


def _get_extension(filename: str) -> str:
    match = re.search(r"(\.[^.]+)$", filename.lower())
    return match.group(1) if match else ""


def _read_csv(data: io.BytesIO, filename: str) -> pd.DataFrame:
    """Intenta leer CSV probando separadores comunes."""
    for sep in [";", ",", "\t", "|"]:
        data.seek(0)
        try:
            df = pd.read_csv(data, sep=sep, decimal=",", thousands=".", encoding="utf-8-sig")
            if df.shape[1] > 1:
                logger.debug("CSV '%s' leído con sep='%s'", filename, sep)
                return df
        except Exception:
            continue

    # Último intento: dejar que pandas auto-detecte
    data.seek(0)
    try:
        df = pd.read_csv(data, sep=None, engine="python", decimal=",", encoding="utf-8-sig")
        logger.debug("CSV '%s' leído con separador auto-detectado", filename)
        return df
    except Exception as e:
        raise ValueError(f"No se pudo parsear CSV '{filename}': {e}") from e


def _read_excel(data: io.BytesIO, filename: str, engine: str) -> pd.DataFrame:
    """Lee archivo Excel con el engine indicado."""
    try:
        df = pd.read_excel(data, engine=engine)
        logger.debug("Excel '%s' leído con engine='%s', shape=%s", filename, engine, df.shape)
        return df
    except Exception as e:
        raise ValueError(f"Error leyendo '{filename}' con engine='{engine}': {e}") from e


# ---------------------------------------------------------------------------
# 3. Validación de umbrales
# ---------------------------------------------------------------------------

def validate_thresholds(config: ThresholdConfig) -> None:
    """Valida que los umbrales globales y por propiedad sean coherentes.

    Args:
        config: Configuración de umbrales a validar.

    Raises:
        ValueError: Si algún umbral es inválido.
    """
    if not (0 <= config.default_green < config.default_yellow):
        raise ValueError(
            f"Umbrales globales inválidos: verde={config.default_green}, "
            f"amarillo={config.default_yellow}. "
            f"Se requiere 0 ≤ verde < amarillo."
        )
    for prop, (green, yellow) in config.thresholds.items():
        if not (0 <= green < yellow):
            raise ValueError(
                f"Umbrales inválidos para '{prop}': verde={green}, amarillo={yellow}. "
                f"Se requiere 0 ≤ verde < amarillo."
            )


# ---------------------------------------------------------------------------
# 4. Cálculo de errores
# ---------------------------------------------------------------------------

def align_dataframes(
    df_isa: pd.DataFrame,
    df_rams: pd.DataFrame,
    key_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Alinea dos DataFrames por la columna clave (cortes).

    Hace un merge outer para preservar todos los cortes de ISA.
    Los cortes de RAMS sin par ISA se descartan (ISA es la referencia).

    Args:
        df_isa: DataFrame ISA (fuente de propiedades y cortes).
        df_rams: DataFrame RAMS (predicciones a validar).
        key_col: Nombre de la columna de corte/índice clave.

    Returns:
        Tupla (df_isa_alineado, df_rams_alineado) con mismo índice.

    Raises:
        ValueError: Si key_col no existe en alguno de los DataFrames.
    """
    for label, df in [("ISA", df_isa), ("RAMS", df_rams)]:
        if key_col not in df.columns:
            raise ValueError(
                f"Columna clave '{key_col}' no encontrada en {label}. "
                f"Columnas disponibles: {list(df.columns)}"
            )

    isa_indexed = df_isa.set_index(key_col)
    rams_indexed = df_rams.set_index(key_col)

    # Reindexar RAMS a los cortes de ISA (ISA es la referencia)
    rams_reindexed = rams_indexed.reindex(isa_indexed.index)

    return isa_indexed, rams_reindexed


def compute_errors(
    df_isa: pd.DataFrame,
    df_rams: pd.DataFrame,
    key_col: str,
    prop_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Calcula errores absolutos |ISA - RAMS| por corte y propiedad.

    Las propiedades y cortes se toman EXCLUSIVAMENTE de ISA.
    Si RAMS no tiene un corte o propiedad, el error es NaN.

    Args:
        df_isa: DataFrame ISA con cortes y propiedades.
        df_rams: DataFrame RAMS con las mismas propiedades.
        key_col: Columna que identifica los cortes (ej. 'corte_C').
        prop_cols: Lista de propiedades a comparar. Si None, usa todas
                   las columnas numéricas de ISA excepto key_col.

    Returns:
        DataFrame de errores absolutos con mismo índice/columnas que ISA.
    """
    isa_idx, rams_idx = align_dataframes(df_isa, df_rams, key_col)

    if prop_cols is None:
        prop_cols = [
            c for c in isa_idx.select_dtypes(include="number").columns
        ]

    # Filtrar columnas existentes en ISA
    prop_cols = [c for c in prop_cols if c in isa_idx.columns]
    if not prop_cols:
        raise ValueError(
            "No se encontraron columnas de propiedades numéricas para comparar."
        )

    isa_num = isa_idx[prop_cols]
    rams_num = rams_idx.reindex(columns=prop_cols)

    # Operación vectorizada
    errors = (isa_num - rams_num).abs()
    logger.debug("Errores calculados: shape=%s, NaNs=%d", errors.shape, errors.isna().sum().sum())
    return errors


# ---------------------------------------------------------------------------
# 5. Clasificación de semáforo
# ---------------------------------------------------------------------------

def classify_semaforo(
    error: float,
    threshold_green: float,
    threshold_yellow: float,
) -> str:
    """Clasifica un error absoluto como verde, amarillo o rojo.

    Args:
        error: Valor absoluto del error |ISA - RAMS|.
        threshold_green: Límite superior (inclusivo) para verde.
        threshold_yellow: Límite superior (inclusivo) para amarillo.

    Returns:
        'verde', 'amarillo' o 'rojo'.

    Raises:
        ValueError: Si los umbrales son incoherentes.
    """
    if threshold_green < 0 or threshold_green >= threshold_yellow:
        raise ValueError(
            f"Umbrales incoherentes: verde={threshold_green}, amarillo={threshold_yellow}"
        )
    if pd.isna(error):
        return "rojo"  # dato faltante → peor caso
    if error <= threshold_green:
        return "verde"
    if error <= threshold_yellow:
        return "amarillo"
    return "rojo"


def classify_matrix(
    error_matrix: pd.DataFrame,
    config: ThresholdConfig,
) -> pd.DataFrame:
    """Aplica classify_semaforo a toda la matriz de errores.

    Args:
        error_matrix: DataFrame de errores absolutos.
        config: Configuración de umbrales por propiedad.

    Returns:
        DataFrame de misma forma con strings 'verde'/'amarillo'/'rojo'.
    """
    result = pd.DataFrame(index=error_matrix.index, columns=error_matrix.columns, dtype=str)
    for col in error_matrix.columns:
        green, yellow = config.get_thresholds(col)
        result[col] = error_matrix[col].apply(
            lambda e: classify_semaforo(e, green, yellow)
        )
    return result


def build_summary(semaforo_matrices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Construye resumen global por crudo.

    Args:
        semaforo_matrices: Mapa nombre_crudo → DataFrame de semáforos.

    Returns:
        DataFrame con columnas: crudo, verde_pct, amarillo_pct, rojo_pct,
        total_celdas, estado_global.
    """
    rows = []
    for name, matrix in semaforo_matrices.items():
        flat = matrix.values.flatten()
        total = len(flat)
        verde = (flat == "verde").sum()
        amarillo = (flat == "amarillo").sum()
        rojo = (flat == "rojo").sum()

        if rojo > 0:
            estado = "rojo"
        elif amarillo > 0:
            estado = "amarillo"
        else:
            estado = "verde"

        rows.append({
            "crudo": name,
            "verde_%": round(100 * verde / total, 1) if total else 0,
            "amarillo_%": round(100 * amarillo / total, 1) if total else 0,
            "rojo_%": round(100 * rojo / total, 1) if total else 0,
            "total_celdas": total,
            "estado_global": estado,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 6. Pipeline completo
# ---------------------------------------------------------------------------

def run_validation(
    isa_files: dict[str, IO[bytes]],
    rams_files: dict[str, IO[bytes]],
    key_col: str,
    config: ThresholdConfig,
    prop_cols: list[str] | None = None,
) -> ValidationResult:
    """Ejecuta el pipeline completo de validación.

    Args:
        isa_files: Mapa nombre_archivo → objeto de archivo ISA.
        rams_files: Mapa nombre_archivo → objeto de archivo RAMS.
        key_col: Columna clave de cortes.
        config: Configuración de umbrales.
        prop_cols: Propiedades a comparar (None = todas las numéricas).

    Returns:
        ValidationResult completo.
    """
    validate_thresholds(config)

    # Emparejar archivos
    paired_map, unpaired_isa, unpaired_rams = pair_files(
        list(isa_files.keys()), list(rams_files.keys())
    )

    result = ValidationResult(unpaired_isa=unpaired_isa, unpaired_rams=unpaired_rams)

    for canon_name, (isa_fname, rams_fname) in paired_map.items():
        try:
            logger.info("Procesando par: %s", canon_name)
            df_isa = read_file(isa_files[isa_fname], isa_fname)
            df_rams = read_file(rams_files[rams_fname], rams_fname)

            errors = compute_errors(df_isa, df_rams, key_col, prop_cols)
            semaforo = classify_matrix(errors, config)

            result.paired_names.append(canon_name)
            result.error_matrices[canon_name] = errors
            result.semaforo_matrices[canon_name] = semaforo

        except Exception as e:
            logger.error("Error procesando '%s': %s", canon_name, e)
            # Reportar como no procesado pero continuar con los demás
            result.unpaired_isa.append(f"{isa_fname} [ERROR: {e}]")

    if result.has_results:
        result.summary = build_summary(result.semaforo_matrices)

    return result


# ---------------------------------------------------------------------------
# 7. Exportación a Excel
# ---------------------------------------------------------------------------

def build_excel(result: ValidationResult, config: ThresholdConfig) -> bytes:
    """Genera un archivo Excel con errores, semáforos y resumen por crudo.

    Usa openpyxl directamente para máxima compatibilidad con Streamlit Cloud.
    No usa pd.Styler (frágil en Cloud).

    Args:
        result: Resultado de validación.
        config: Configuración de umbrales (para leyenda).

    Returns:
        Bytes del archivo Excel listo para descarga.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # eliminar hoja vacía por defecto

    # Hoja resumen
    _write_summary_sheet(wb, result)

    # Hoja por cada crudo: errores + semáforo
    for name in result.paired_names:
        error_df = result.error_matrices[name]
        semaforo_df = result.semaforo_matrices[name]
        sheet_name = name[:28]  # Excel limita 31 chars; dejar margen
        _write_crudo_sheet(wb, sheet_name, error_df, semaforo_df)

    # Hoja de leyenda/configuración
    _write_legend_sheet(wb, config)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _write_summary_sheet(wb: openpyxl.Workbook, result: ValidationResult) -> None:
    ws = wb.create_sheet("Resumen")
    if result.summary.empty:
        ws.cell(1, 1, "Sin resultados")
        return

    headers = list(result.summary.columns)
    _write_header_row(ws, headers, row=1)

    for r_idx, row in enumerate(result.summary.itertuples(index=False), start=2):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(r_idx, c_idx, val)
            # Colorear columna estado_global
            if headers[c_idx - 1] == "estado_global":
                cell.fill = _semaforo_fill(str(val))

    _auto_width(ws)


def _write_crudo_sheet(
    wb: openpyxl.Workbook,
    sheet_name: str,
    error_df: pd.DataFrame,
    semaforo_df: pd.DataFrame,
) -> None:
    ws = wb.create_sheet(sheet_name)
    cols = list(error_df.columns)

    # Cabecera
    ws.cell(1, 1, "corte")
    _write_header_row(ws, cols, row=1, col_offset=1)

    for r_idx, (idx_val, err_row) in enumerate(error_df.iterrows(), start=2):
        ws.cell(r_idx, 1, idx_val)
        for c_idx, col in enumerate(cols, start=2):
            error_val = err_row[col]
            semaforo_val = semaforo_df.loc[idx_val, col] if idx_val in semaforo_df.index else "rojo"
            cell = ws.cell(r_idx, c_idx)
            cell.value = round(float(error_val), 4) if not pd.isna(error_val) else "N/D"
            cell.fill = _semaforo_fill(str(semaforo_val))
            cell.alignment = Alignment(horizontal="center")

    _auto_width(ws)


def _write_legend_sheet(wb: openpyxl.Workbook, config: ThresholdConfig) -> None:
    ws = wb.create_sheet("Leyenda")
    rows = [
        ["Semáforo", "Criterio"],
        ["🟢 Verde", f"Error ≤ {config.default_green}"],
        ["🟡 Amarillo", f"{config.default_green} < Error ≤ {config.default_yellow}"],
        ["🔴 Rojo", f"Error > {config.default_yellow} o dato faltante"],
    ]
    for r_idx, row in enumerate(rows, start=1):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(r_idx, c_idx, val)
            if r_idx > 1:
                semaforo = ["verde", "amarillo", "rojo"][r_idx - 2]
                cell.fill = _semaforo_fill(semaforo)
            else:
                cell.font = Font(bold=True)
    _auto_width(ws)


def _write_header_row(
    ws, headers: list[str], row: int = 1, col_offset: int = 0
) -> None:
    header_fill = PatternFill("solid", fgColor="FF1E3A5F")
    header_font = Font(bold=True, color="FFFFFFFF")
    for c_idx, h in enumerate(headers, start=1 + col_offset):
        cell = ws.cell(row, c_idx, h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")


def _semaforo_fill(semaforo: str) -> PatternFill:
    color = SEMAFORO_COLORS.get(semaforo, "FFCCCCCC")
    return PatternFill("solid", fgColor=color)


def _auto_width(ws) -> None:
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 40)
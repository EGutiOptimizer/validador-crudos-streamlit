# core/validator_core.py
# -*- coding: utf-8 -*-
import io
import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple, Iterable

import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import PatternFill, Font
from openpyxl.formatting.rule import Rule
from openpyxl.styles.differential import DifferentialStyle

# ===========
# Logging
# ===========
def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

# ===========
# Utilidades de normalización
# ===========
def strip_accents(text: str) -> str:
    if text is None:
        return ""
    text = str(text)
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

def canon_prop(s: str, alias: Optional[Dict[str, str]] = None) -> str:
    if s is None:
        return ""
    t = strip_accents(str(s)).upper().strip()
    for ch in ['.', 'º', '°']:
        t = t.replace(ch, '')
    t = re.sub(r"\s+", " ", t)
    if not re.search(r"[A-Z0-9]", t):
        return ""
    if alias:
        return alias.get(t, t)
    return t

def canon_corte(s: str) -> str:
    if s is None:
        return ""
    t = str(s)
    t = t.replace('\u00A0', ' ')
    t = ''.join(' ' if unicodedata.category(c) == 'Zs' else c for c in t)
    for dash in ['\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2212']:
        t = t.replace(dash, '-')
    t = t.replace('º', '').replace('°', '')
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s+", "", t).upper()
    return t

# ===========
# Detección/umbrales
# ===========
def detectar_columna_tipo(df: pd.DataFrame) -> Optional[str]:
    for col in df.columns:
        name = str(col).strip().lower()
        if name in {"tipo", "columna1", "categoria", "categoría"}:
            return col
    sample_cols = [c for c in df.columns if str(c).strip().lower() not in {"propiedad", "unidad"}]
    for col in sample_cols:
        try:
            serie = df[col].astype(str).str.upper().str.strip()
            if serie.head(50).str.contains(r"REPRO|ADMISIBLE|REPET").any():
                return col
        except Exception:
            pass
    return None

def normalizar_tipo(raw: str) -> str:
    if pd.isna(raw):
        return ""
    t = str(raw)
    t = t.replace('*', '')
    t = t.replace('\u00A0', ' ')
    t = strip_accents(t).upper().strip()
    return t

def construir_umbrales(df: pd.DataFrame, alias_prop: Dict[str, str]) -> Dict[Tuple[str, str], float]:
    col_prop = next((c for c in df.columns if str(c).strip().lower() == 'propiedad'), None)
    if col_prop is None:
        raise ValueError("La matriz de umbrales no tiene columna 'Propiedad'.")
    col_tipo = detectar_columna_tipo(df)
    if col_tipo is None:
        raise ValueError("No se localiza columna 'Tipo' en la matriz de umbrales.")

    cortes_cols: List[Tuple[str, str]] = []
    for c in df.columns:
        if c in {col_prop, col_tipo}:
            continue
        cc = canon_corte(str(c))
        if cc in {"", "UNIDAD", "CRUDO"}:
            continue
        cortes_cols.append((str(c), cc))

    umbrales: Dict[Tuple[str, str], float] = {}
    prop_actual = ""

    for _, row in df.iterrows():
        prop_raw = row.get(col_prop)
        prop_canon = canon_prop(prop_raw, alias_prop)
        if prop_canon:
            prop_actual = prop_canon
        if not prop_actual:
            continue
        tipo = normalizar_tipo(row.get(col_tipo))
        if not ("REPRO" in tipo or "ADMISIBLE" in tipo or "REPET" in tipo):
            continue

        for col_o, cc in cortes_cols:
            val = row.get(col_o)
            if pd.isna(val):
                continue
            vs = str(val).strip()
            if vs == "":
                continue
            try:
                v = float(vs.replace(',', '.'))
            except Exception:
                continue
            key = (prop_actual, cc)
            if key in umbrales:
                if v > umbrales[key]:
                    umbrales[key] = v
            else:
                umbrales[key] = v
    return umbrales

# ===========
# Reglas
# ===========
def es_corte_pesado(corte: str) -> bool:
    s = corte.upper().strip()
    if any(tag in s for tag in ["C6", "C7", "C8", "C9", "C10"]):
        return True
    if s.endswith('+'):
        try:
            base = float(s[:-1])
            return base >= 299
        except Exception:
            return False
    if '-' in s:
        try:
            start = float(s.split('-')[0])
            return start >= 299
        except Exception:
            return False
    return False

def estado_corte(valor: float, umbral: float, tol: float) -> int:
    if valor <= umbral:
        return 0
    elif valor <= umbral * (1.0 + tol):
        return 1
    else:
        return 2

def _prop_base_para_umbral(prop_canon: str) -> str:
    if prop_canon == "PESO ACUMULADO":
        return "PESO"
    return prop_canon

def _buscar_umbral(
    umbrales: Dict[Tuple[str, str], float],
    prop_canon: str,
    corte_key: str
) -> Optional[float]:
    thr = umbrales.get((prop_canon, corte_key))
    if thr is not None:
        return thr
    base_prop = _prop_base_para_umbral(prop_canon)
    if base_prop != prop_canon:
        thr2 = umbrales.get((base_prop, corte_key))
        if thr2 is not None:
            return thr2
    return None

def clasificar_propiedad(
    errores_fila: Dict[str, float],
    prop_canon: str,
    umbrales: Dict[Tuple[str, str], float],
    tol: float,
    pct_ok_amarillo: float,
    pct_rojo_rojo: float,
    tol_pesados: float = 0.6,
    tol_azufre_verde: float = 2.0,
    tol_densidad_verde: float = 2.0,
):
    estados: Dict[str, str] = {}
    total_con_valor = 0
    total_valid = 0
    n_verde = n_amarillo = n_rojo = 0
    rojo_absoluto = False

    corte_peor = None
    error_peor = None
    umbral_peor = None
    ratio_peor = -1.0

    base_prop = _prop_base_para_umbral(prop_canon)
    tiene_umbral_prop = any(k[0] == base_prop for k in umbrales.keys())

    for corte, valor in errores_fila.items():
        if valor is None or (isinstance(valor, float) and pd.isna(valor)):
            estados[corte] = "(no numérico)"
            continue
        try:
            v = float(str(valor).replace(",", "."))
        except Exception:
            estados[corte] = "(no numérico)"
            continue

        total_con_valor += 1

        cc = canon_corte(corte)
        thr = _buscar_umbral(umbrales, prop_canon, cc)
        if thr is None:
            thr = _buscar_umbral(umbrales, prop_canon, corte)
        if thr is None:
            estados[corte] = "(sin umbral)"
            continue

        total_valid += 1

        try:
            ratio = v / thr
        except ZeroDivisionError:
            ratio = float("inf")

        if ratio > ratio_peor:
            ratio_peor = ratio
            corte_peor = corte
            error_peor = v
            umbral_peor = thr

        if v > 3 * thr:
            estados[corte] = "ROJO"; n_rojo += 1; rojo_absoluto = True
            continue

        if prop_canon in ("AZUFRE", "DENSIDAD", "DENSIDAD A 15C", "DENSIDAD A 15"):
            if v <= 3 * thr:
                estados[corte] = "VERDE"; n_verde += 1
            elif 2 * thr < v <= 3 * thr:
                estados[corte] = "AMARILLO"; n_amarillo += 1
            else:
                estados[corte] = "ROJO"; n_rojo += 1
            continue

        tol_local = tol_pesados if es_corte_pesado(corte) else tol
        umbral_verde = thr
        umbral_amarillo = thr * (1 + tol_local)

        if v <= umbral_verde:
            estados[corte] = "VERDE"; n_verde += 1
        elif v <= umbral_amarillo:
            estados[corte] = "AMARILLO"; n_amarillo += 1
        else:
            estados[corte] = "ROJO"; n_rojo += 1

    if total_con_valor == 0:
        return "", estados, corte_peor, error_peor, ratio_peor, umbral_peor
    if not tiene_umbral_prop or total_valid == 0:
        return "NA", estados, corte_peor, error_peor, ratio_peor, umbral_peor

    if rojo_absoluto:
        return "ROJO", estados, corte_peor, error_peor, ratio_peor, umbral_peor

    verde_pct = n_verde / total_valid
    rojo_pct = n_rojo / total_valid

    if rojo_pct > pct_rojo_rojo:
        return "ROJO", estados, corte_peor, error_peor, ratio_peor, umbral_peor
    if verde_pct >= pct_ok_amarillo:
        return "VERDE", estados, corte_peor, error_peor, ratio_peor, umbral_peor
    return "AMARILLO", estados, corte_peor, error_peor, ratio_peor, umbral_peor

# ===========
# Lectura de tablas (desde bytes / nombres)
# ===========
def leer_tabla_errores_filelike(file_bytes: bytes, filename: str, sheet: Optional[str] = None) -> pd.DataFrame:
    ext = os.path.splitext(filename)[1].lower()
    bio = io.BytesIO(file_bytes)
    if ext in {".xlsx", ".xls"}:
        try:
            return pd.read_excel(bio, sheet_name=sheet or 0, engine="openpyxl")
        except Exception:
            bio.seek(0)
            try:
                # xlrd >= 2.0 sólo soporta .xls; si el archivo es xlsx fallará (es normal)
                return pd.read_excel(bio, sheet_name=sheet or 0, engine="xlrd")
            except Exception:
                bio.seek(0)
                try:
                    return pd.read_excel(bio, sheet_name=sheet or 0, engine="pyxlsb")
                except Exception as e:
                    raise ValueError(f"No se pudo leer {filename} con ningún engine válido: {e}")
    elif ext == ".csv":
        return pd.read_csv(bio, sep=",", decimal=",", engine="python", encoding="utf-8")
    else:
        raise ValueError(f"Archivo no soportado: {filename}")

def detectar_cortes_en_df(df: pd.DataFrame) -> List[Tuple[str, str]]:
    cortes = []
    for c in df.columns:
        cname = str(c)
        low = cname.strip().lower()
        if low in {"propiedad", "unidad", "validacion", "validación", "validacion auto", "validación auto"}:
            continue
        cc = canon_corte(cname)
        if cc:
            cortes.append((cname, cc))
    return cortes

def crear_semantica_alias() -> Dict[str, str]:
    raw = {
        "PESO": "PESO",
        "PESO ACUMULADO": "PESO ACUMULADO",
        "DENSIDAD": "DENSIDAD",
        "DENSIDAD A 15C": "DENSIDAD",
        "DENSIDAD A 15": "DENSIDAD",
        "DENSIDAD 15C": "DENSIDAD",
        "VISCOSIDAD 50": "VISCOSIDAD 50",
        "VISCOSIDAD 50C": "VISCOSIDAD 50",
        "VISCOSIDAD A 50C": "VISCOSIDAD 50",
        "VISCOSIDAD 100": "VISCOSIDAD 100",
        "VISCOSIDAD 100C": "VISCOSIDAD 100",
        "VISCOSIDAD A 100C": "VISCOSIDAD 100",
        "AZUFRE": "AZUFRE",
        "AZUFRE MERCAPTANO": "AZUFRE MERCAPTANO",
        "RON": "RON", "NOR": "RON", "NOR CLARO": "RON", "N O R CLARO": "RON",
        "MON": "MON", "NOM": "MON", "NOM CLARO": "MON", "N O M CLARO": "MON",
        "N DE NEUTRALIZACION": "N DE NEUTRALIZACION",
        "NUMERO DE NEUTRALIZACION": "N DE NEUTRALIZACION",
        "NO DE NEUTRALIZACION": "N DE NEUTRALIZACION",
        "INDICE DE REFRACCION 70C": "INDICE DE REFRACCION 70C",
        "PUNTO DE VERTIDO": "PUNTO DE VERTIDO",
        "PUNTO DE NIEBLA": "PUNTO DE NIEBLA",
        "PUNTO DE CRISTALIZACION": "PUNTO DE CRISTALIZACION",
        "PUNTO DE ANILINA": "PUNTO DE ANILINA",
        "PIONA (%VOL), N-PARAFINAS": "PIONA N-PARAFINAS",
        "PIONA (%VOL), I-PARAFINAS": "PIONA I-PARAFINAS",
        "PIONA (%VOL), NAFTENOS": "PIONA NAFTENOS",
        "PIONA (%VOL), POLINAFTENOS": "PIONA POLINAFTENOS",
        "PIONA (%VOL), AROMATICOS": "PIONA AROMATICOS",
        "PIONA (%VOL), SUPERIORES A 200C": "PIONA SUPERIORES A 200C",
        "PIONA N-PARAFINAS": "PIONA N-PARAFINAS",
        "PIONA I-PARAFINAS": "PIONA I-PARAFINAS",
        "PIONA NAFTENOS": "PIONA NAFTENOS",
        "PIONA POLINAFTENOS": "PIONA POLINAFTENOS",
        "PIONA AROMATICOS": "PIONA AROMATICOS",
        "PIONA SUPERIORES A 200C": "PIONA SUPERIORES A 200C",
        "PIONA, N-PARAFINAS": "PIONA N-PARAFINAS",
        "PIONA, I-PARAFINAS": "PIONA I-PARAFINAS",
        "PIONA, NAFTENOS": "PIONA NAFTENOS",
        "PIONA, POLINAFTENOS": "PIONA POLINAFTENOS",
        "PIONA, AROMATICOS": "PIONA AROMATICOS",
        "PIONA, SUPERIORES A 200C": "PIONA SUPERIORES A 200C",
        "NITROGENO": "NITROGENO",
        "NITROGENO BASICO": "NITROGENO BASICO",
        "RESIDUO DE CARBON": "RESIDUO DE CARBON",
        "CARBONO CONRADSON": "RESIDUO DE CARBON",
        "ASFALTENOS": "ASFALTENOS",
        "MONOAROMATICOS": "MONOAROMATICOS",
        "DIAROMATICOS": "DIAROMATICOS",
        "TRIAROMATICOS Y SUPERIORES": "TRIAROMATICOS",
        "CONTENIDO EN C2": "CONTENIDO EN C2",
        "CONTENIDO EN C3": "CONTENIDO EN C3",
        "CONTENIDO EN IC4": "CONTENIDO EN IC4",
        "CONTENIDO EN NC4": "CONTENIDO EN NC4",
        "NIQUEL": "NIQUEL",
        "VANADIO": "VANADIO",
        "SILICIO": "SILICIO",
    }

    def _norm(s: str) -> str:
        if s is None:
            return ""
        t = strip_accents(str(s)).upper().strip()
        for ch in ['.', 'º', '°']:
            t = t.replace(ch, '')
        t = re.sub(r"\s+", " ", t)
        return t

    out: Dict[str, str] = {}
    for k, v in raw.items():
        out[_norm(k)] = _norm(v)
    return out

# ===========
# Excel (formato)
# ===========
def add_conditional_formatting_text(ws, cell_range: str):
    fill_verde = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    fill_amar = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    fill_rojo = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    fill_gris = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

    dxf_v = DifferentialStyle(fill=fill_verde)
    dxf_a = DifferentialStyle(fill=fill_amar)
    dxf_r = DifferentialStyle(fill=fill_rojo)
    dxf_g = DifferentialStyle(fill=fill_gris)

    rule_v = Rule(type="containsText", operator="containsText", text="VERDE", dxf=dxf_v)
    rule_a = Rule(type="containsText", operator="containsText", text="AMARILLO", dxf=dxf_a)
    rule_r = Rule(type="containsText", operator="containsText", text="ROJO", dxf=dxf_r)
    rule_n = Rule(type="containsText", operator="containsText", text="NA", dxf=dxf_g)

    ws.conditional_formatting.add(cell_range, rule_v)
    ws.conditional_formatting.add(cell_range, rule_a)
    ws.conditional_formatting.add(cell_range, rule_r)
    ws.conditional_formatting.add(cell_range, rule_n)

def escribir_hoja_df(ws, df: pd.DataFrame):
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for col in ws.columns:
        max_len = max((len(str(cell.value)) if cell.value is not None else 0) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, max_len + 2), 45)

# ===========
# Motor (adaptado a DataFrames / filelikes)
# ===========
def _nombre_base_crudo(fname: str) -> str:
    base = os.path.splitext(os.path.basename(fname))[0]
    m = re.search(r"([A-Za-z]{3}-\d{4}-\d+)", base)
    if m:
        return m.group(1).upper()
    base = re.sub(r"^(?:ISA|RAMS)[_\-]+", "", base, flags=re.IGNORECASE)
    base = re.sub(r"([_\-])(ISA|RAMS)(?:([_\-]?v?\d{1,3})?)$", "", base, flags=re.IGNORECASE)
    base = re.sub(r"([_\-])(ISA|RAMS)(?:[_\-].*)?$", "", base, flags=re.IGNORECASE)
    return base.strip("_- ")

def _indice_prop(df: pd.DataFrame, alias_prop: Dict[str, str]) -> Dict[str, int]:
    idx = {}
    if 'Propiedad' not in df.columns:
        return idx
    for i, v in enumerate(df['Propiedad'].tolist()):
        p = canon_prop(v, alias_prop)
        if p:
            idx[p] = i
    return idx

def _mapa_cortes(df: pd.DataFrame) -> Dict[str, str]:
    out = {}
    for c in df.columns:
        cc = canon_corte(c)
        low = str(c).strip().lower()
        if cc and low not in {"propiedad", "unidad", "validacion", "validación", "validacion auto", "validación auto"}:
            out[cc] = c
    return out

def _float_or_none(x):
    if x is None:
        return None
    try:
        s = str(x).strip()
        if s == "":
            return None
        return float(s.replace(",", "."))
    except Exception:
        return None

def calcular_errores_crudo_df(
    df_isa: pd.DataFrame,
    df_rams: pd.DataFrame,
    path_isa_name: str,
    umbrales: Dict[Tuple[str, str], float],
    alias_prop: Dict[str, str],
    tol: float,
    pct_ok_amarillo: float,
    pct_rojo_rojo: float,
    tol_pesados: float,
    hoja_resumen: Dict[str, Dict[str, str]],
) -> Tuple[str, pd.DataFrame, List[str], List[str]]:
    if 'Propiedad' not in df_isa.columns:
        raise ValueError(f"{path_isa_name} no tiene columna 'Propiedad'.")
    if 'Propiedad' not in df_rams.columns:
        raise ValueError(f"RAMS no tiene columna 'Propiedad'.")

    cortes_isa = detectar_cortes_en_df(df_isa)
    if not cortes_isa:
        raise ValueError(f"{path_isa_name} no contiene cortes reconocibles.")

    idx_rams = _indice_prop(df_rams, alias_prop)
    cortes_map_rams = _mapa_cortes(df_rams)

    columnas_cortes_visibles = [cname for (cname, _cc) in cortes_isa]
    df_out_cols = ["Propiedad", "Semaforo", "Corte_peor", "Error_peor", "Umbral_peor"] + columnas_cortes_visibles
    df_out = pd.DataFrame(columns=df_out_cols)

    crude_name = _nombre_base_crudo(path_isa_name)
    hoja_name = crude_name[:31]
    orden_props_local = []

    for _, row_isa in df_isa.iterrows():
        prop_raw = row_isa.get("Propiedad")
        prop_canon = canon_prop(prop_raw, alias_prop)
        if not prop_canon:
            continue
        orden_props_local.append(prop_canon)
        if prop_canon not in idx_rams:
            continue

        row_rams = df_rams.iloc[idx_rams[prop_canon]]

        errores_fila: Dict[str, float] = {}
        fila_out = {"Propiedad": str(prop_raw)}

        for (cname_isa, cc_isa) in cortes_isa:
            col_rams = cortes_map_rams.get(cc_isa)
            if col_rams is None:
                fila_out[cname_isa] = None
                continue
            isa_val = _float_or_none(row_isa.get(cname_isa))
            rams_val = _float_or_none(row_rams.get(col_rams))
            err = abs(isa_val - rams_val) if (isa_val is not None and rams_val is not None) else None
            errores_fila[cc_isa] = err
            fila_out[cname_isa] = err

        sem, _estados, corte_peor, error_peor, _ratio, umbral_peor = clasificar_propiedad(
            errores_fila,
            prop_canon,
            umbrales,
            tol=tol,
            pct_ok_amarillo=pct_ok_amarillo,
            pct_rojo_rojo=pct_rojo_rojo,
            tol_pesados=tol_pesados,
        )

        fila_out["Semaforo"] = sem
        fila_out["Corte_peor"] = corte_peor
        fila_out["Error_peor"] = error_peor
        fila_out["Umbral_peor"] = umbral_peor

        hoja_resumen.setdefault(prop_canon, {})[crude_name] = sem
        df_out.loc[len(df_out)] = fila_out

    return hoja_name, df_out, columnas_cortes_visibles, orden_props_local

def _sem_global_por_crudo(
    resumen: Dict[str, Dict[str, str]],
    pct_ok_amarillo: float,
    pct_rojo_rojo: float,
) -> Dict[str, str]:
    crudos = sorted({c for m in resumen.values() for c in m.keys()})
    out = {c: "" for c in crudos}
    for cr in crudos:
        vals = [m.get(cr, "") for m in resumen.values()]
        vals = [v for v in vals if v in {"VERDE", "AMARILLO", "ROJO"}]
        if not vals:
            out[cr] = ""
            continue
        total = len(vals)
        verde = sum(1 for v in vals if v == "VERDE")
        rojo = sum(1 for v in vals if v == "ROJO")
        rojo_pct = rojo / total
        verde_pct = verde / total
        if rojo_pct > pct_rojo_rojo:
            out[cr] = "ROJO"
        elif verde_pct >= pct_ok_amarillo:
            out[cr] = "VERDE"
        else:
            out[cr] = "AMARILLO"
    return out

def exportar_resultados_a_bytes(
    hojas_crudos: List[Tuple[str, pd.DataFrame]],
    resumen: Dict[str, Dict[str, str]],
    orden_propiedades: List[str],
    pct_ok_amarillo: float,
    pct_rojo_rojo: float,
) -> bytes:
    wb = Workbook()
    ws0 = wb.active
    ws0.title = "Resumen"

    todos_crudos = sorted({c for m in resumen.values() for c in m.keys()})
    global_por_crudo = _sem_global_por_crudo(resumen, pct_ok_amarillo, pct_rojo_rojo)

    data = []
    if todos_crudos:
        row_global = {"Propiedad": "GLOBAL"}
        for cr in todos_crudos:
            row_global[cr] = global_por_crudo.get(cr, "")
        data.append(row_global)

    for prop in orden_propiedades:
        if prop in resumen:
            row = {"Propiedad": prop}
            for cr in todos_crudos:
                row[cr] = resumen[prop].get(cr, "")
            data.append(row)

    df_res = pd.DataFrame(data) if data else pd.DataFrame(columns=["Propiedad"])
    escribir_hoja_df(ws0, df_res)

    if df_res.shape[0] > 0 and len(todos_crudos) > 0:
        from openpyxl.utils import get_column_letter
        start_row = 2
        end_row = df_res.shape[0] + 1
        for j in range(2, 2 + len(todos_crudos)):
            col_letter = get_column_letter(j)
            add_conditional_formatting_text(ws0, f"{col_letter}{start_row}:{col_letter}{end_row}")

    for hoja, df_out in hojas_crudos:
        ws = wb.create_sheet(title=hoja)
        escribir_hoja_df(ws, df_out)
        if df_out.shape[0] > 0:
            start_row = 2
            end_row = df_out.shape[0] + 1
            add_conditional_formatting_text(ws, f"B{start_row}:B{end_row}")

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()

def emparejar_subidos(
    isa_files: Iterable[Tuple[str, bytes]],
    rams_files: Iterable[Tuple[str, bytes]]
) -> List[Tuple[Tuple[str, bytes], Tuple[str, bytes]]]:
    """
    Recibe listas de (filename, bytes) para ISA y RAMS, y devuelve pares emparejados por nombre base.
    """
    def _map(files):
        out = {}
        for name, b in files:
            base = _nombre_base_crudo(name)
            out[base] = (name, b)
        return out

    isa_map = _map(isa_files)
    rams_map = _map(rams_files)
    comunes = sorted(set(isa_map.keys()) & set(rams_map.keys()))
    return [(isa_map[b], rams_map[b]) for b in comunes]

def run_validation_in_memory(
    matriz_bytes: bytes, matriz_name: str, matriz_sheet: Optional[str],
    isa_files: Iterable[Tuple[str, bytes]],
    rams_files: Iterable[Tuple[str, bytes]],
    tolerancia: float = 0.1,
    pct_ok_amarillo: float = 0.9,
    pct_rojo_rojo: float = 0.30,
    tol_pesados: float = 0.60,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, str]], List[Tuple[str, pd.DataFrame]], List[str], bytes]:
    """
    Orquesta todo:
    - Lee matriz de umbrales
    - Empareja archivos
    - Calcula hojas por crudo y resumen
    - Devuelve:
        df_resumen_visual, resumen_dict, hojas, orden_propiedades, excel_bytes
    """
    alias_prop = crear_semantica_alias()
    df_matriz = leer_tabla_errores_filelike(matriz_bytes, matriz_name, sheet=matriz_sheet)
    umbrales = construir_umbrales(df_matriz, alias_prop)

    pares = emparejar_subidos(isa_files, rams_files)
    if not pares:
        raise ValueError("No se han encontrado pares ISA/RAMS con nombres base comunes.")

    resumen: Dict[str, Dict[str, str]] = {}
    hojas: List[Tuple[str, pd.DataFrame]] = []
    orden_propiedades: List[str] = []

    for (isa_name, isa_b), (_rams_name, rams_b) in pares:
        df_isa = leer_tabla_errores_filelike(isa_b, isa_name, sheet=None)
        df_rams = leer_tabla_errores_filelike(rams_b, _rams_name, sheet=None)
        hoja_name, df_out, _cortes_vis, orden_local = calcular_errores_crudo_df(
            df_isa=df_isa,
            df_rams=df_rams,
            path_isa_name=isa_name,
            umbrales=umbrales,
            alias_prop=alias_prop,
            tol=tolerancia,
            pct_ok_amarillo=pct_ok_amarillo,
            pct_rojo_rojo=pct_rojo_rojo,
            tol_pesados=tol_pesados,
            hoja_resumen=resumen,
        )
        if not orden_propiedades:
            orden_propiedades = orden_local
        hojas.append((hoja_name, df_out))

    # Construir DataFrame resumen para UI (igual que Excel pero en pandas)
    todos_crudos = sorted({c for m in resumen.values() for c in m.keys()})
    data = []
    # Fila GLOBAL
    if todos_crudos:
        global_por_crudo = _sem_global_por_crudo(resumen, pct_ok_amarillo, pct_rojo_rojo)
        row_global = {"Propiedad": "GLOBAL", **{cr: global_por_crudo.get(cr, "") for cr in todos_crudos}}
        data.append(row_global)
    for prop in orden_propiedades:
        if prop in resumen:
            data.append({"Propiedad": prop, **{cr: resumen[prop].get(cr, "") for cr in todos_crudos}})

    df_resumen = pd.DataFrame(data) if data else pd.DataFrame(columns=["Propiedad"])

    excel_bytes = exportar_resultados_a_bytes(
        hojas_crudos=hojas,
        resumen=resumen,
        orden_propiedades=orden_propiedades,
        pct_ok_amarillo=pct_ok_amarillo,
        pct_rojo_rojo=pct_rojo_rojo,
    )
    return df_resumen, resumen, hojas, orden_propiedades, excel_bytes
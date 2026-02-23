"""
tests/test_validator_core.py
============================
Tests unitarios para la lógica core del validador.
Ejecutar con: pytest -q

Incluye:
  - Tests de compatibilidad con la versión anterior (tests 1-10)
  - Tests nuevos de paridad con el MVP (tests 11-18)
"""
from __future__ import annotations

import io
import pytest
import pandas as pd
import numpy as np

from core.models import ThresholdConfig, ValidationResult
from core.validator_core import (
    # Funciones de normalización (MVP)
    strip_accents,
    canon_prop,
    canon_corte,
    # Emparejamiento MVP
    _nombre_base_crudo,
    pair_files,
    # Lectura
    read_file,
    # Reglas de evaluación (MVP)
    es_corte_pesado,
    _buscar_umbral,
    _prop_base_para_umbral,
    clasificar_propiedad,
    # Umbrales (MVP)
    detectar_columna_tipo,
    normalizar_tipo,
    construir_umbrales,
    crear_semantica_alias,
    # Pipeline
    calcular_errores_crudo_df,
    _sem_global_por_crudo,
    _build_summary_df,
    validate_params,
    build_excel,
    run_validation,
    # Alias compat
    canonize_name,
    validate_thresholds,
    # Constantes
    SEMAFORO_COLORS,
    SEMAFORO_LABELS,
    SUPPORTED_EXTENSIONS,
    DEFAULT_TOL,
    DEFAULT_TOL_PESADOS,
    DEFAULT_PCT_OK_AMARILLO,
    DEFAULT_PCT_ROJO_ROJO,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def alias_prop():
    return crear_semantica_alias()


@pytest.fixture
def simple_isa() -> pd.DataFrame:
    return pd.DataFrame({
        "Propiedad": ["Densidad", "Viscosidad", "Azufre"],
        "150-200": [850.0, 5.0, 0.10],
        "200-250": [860.0, 6.0, 0.20],
        "300-350": [870.0, 7.0, 0.35],
    })


@pytest.fixture
def simple_rams() -> pd.DataFrame:
    return pd.DataFrame({
        "Propiedad": ["Densidad", "Viscosidad", "Azufre"],
        "150-200": [851.0, 5.5, 0.11],
        "200-250": [858.5, 6.0, 0.22],
        "300-350": [872.0, 6.5, 0.36],
    })


@pytest.fixture
def simple_umbrales(alias_prop) -> dict:
    """Umbrales mínimos para las propiedades del fixture."""
    return {
        ("DENSIDAD", "150-200"): 2.0,
        ("DENSIDAD", "200-250"): 2.0,
        ("DENSIDAD", "300-350"): 2.0,
        ("VISCOSIDAD 50", "150-200"): 1.0,
        ("VISCOSIDAD 50", "200-250"): 1.0,
        ("VISCOSIDAD 50", "300-350"): 1.0,
        ("AZUFRE", "150-200"): 0.05,
        ("AZUFRE", "200-250"): 0.05,
        ("AZUFRE", "300-350"): 0.05,
    }


@pytest.fixture
def isa_bytes(simple_isa) -> bytes:
    buf = io.BytesIO()
    simple_isa.to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def rams_bytes(simple_rams) -> bytes:
    buf = io.BytesIO()
    simple_rams.to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def matriz_bytes(simple_umbrales) -> bytes:
    """Genera un Excel de umbrales mínimo compatible con construir_umbrales."""
    rows = [
        {"Propiedad": "DENSIDAD", "Tipo": "Reproductibilidad",
         "150-200": 2.0, "200-250": 2.0, "300-350": 2.0},
        {"Propiedad": "VISCOSIDAD 50", "Tipo": "Reproductibilidad",
         "150-200": 1.0, "200-250": 1.0, "300-350": 1.0},
        {"Propiedad": "AZUFRE", "Tipo": "Reproductibilidad",
         "150-200": 0.05, "200-250": 0.05, "300-350": 0.05},
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


# ===========================================================================
# 1. Tests strip_accents
# ===========================================================================

class TestStripAccents:

    def test_removes_accents(self):
        assert strip_accents("Densidád") == "Densidad"

    def test_none_returns_empty(self):
        assert strip_accents(None) == ""

    def test_no_accents_unchanged(self):
        assert strip_accents("DENSIDAD") == "DENSIDAD"

    def test_multiple_accents(self):
        result = strip_accents("Propiétion Núméro")
        assert result == "Propiétion Numero".replace("é", "e")


# ===========================================================================
# 2. Tests canon_prop
# ===========================================================================

class TestCanonProp:

    def test_basic(self):
        assert canon_prop("Densidad") == "DENSIDAD"

    def test_removes_degree(self):
        assert canon_prop("Densidad a 15°C") == "DENSIDAD A 15C"

    def test_alias_applied(self):
        alias = crear_semantica_alias()
        assert canon_prop("NOR CLARO", alias) == "RON"

    def test_alias_carbono_conradson(self):
        alias = crear_semantica_alias()
        assert canon_prop("Carbono Conradson", alias) == "RESIDUO DE CARBON"

    def test_none_returns_empty(self):
        assert canon_prop(None) == ""

    def test_only_symbols_returns_empty(self):
        assert canon_prop("---") == ""


# ===========================================================================
# 3. Tests canon_corte
# ===========================================================================

class TestCanonCorte:

    def test_basic_range(self):
        assert canon_corte("150-200") == "150-200"

    def test_typographic_dash(self):
        assert canon_corte("150\u2013200") == "150-200"

    def test_spaces_around_dash(self):
        assert canon_corte("150 - 200") == "150-200"

    def test_removes_degrees(self):
        assert canon_corte("150°-200°") == "150-200"

    def test_plus_corte(self):
        assert canon_corte("538+") == "538+"

    def test_none_returns_empty(self):
        assert canon_corte(None) == ""


# ===========================================================================
# 4. Tests es_corte_pesado
# ===========================================================================

class TestEsCorteePesado:

    @pytest.mark.parametrize("corte,expected", [
        ("C6-C10", True),
        ("C7", True),
        ("538+", True),
        ("300-350", True),
        ("298-350", False),
        ("150-200", False),
        ("IBP-150", False),
    ])
    def test_parametrized(self, corte, expected):
        assert es_corte_pesado(corte) == expected

    def test_exact_boundary_299(self):
        assert es_corte_pesado("299-350") is True

    def test_exact_boundary_298(self):
        assert es_corte_pesado("298-350") is False


# ===========================================================================
# 5. Tests nombre_base_crudo  (MVP logic)
# ===========================================================================

class TestNombreBaseCrudo:

    @pytest.mark.parametrize("fname,expected", [
        ("ISA_Crudo_Maya.xlsx", "Crudo_Maya"),
        ("RAMS_Crudo_Maya.xlsx", "Crudo_Maya"),
        ("Crudo_Maya_ISA.xlsx", "Crudo_Maya"),
        ("GMX-2023-1_ISA_v1.xlsx", "GMX-2023-1"),
        ("RAMS_GMX-2023-1.xlsx", "GMX-2023-1"),
        ("COL-2023-1.xlsx", "COL-2023-1"),
    ])
    def test_parametrized(self, fname, expected):
        assert _nombre_base_crudo(fname) == expected

    def test_strips_isa_prefix(self):
        result = _nombre_base_crudo("ISA_Maya.xlsx")
        assert "isa" not in result.lower()

    def test_strips_rams_prefix(self):
        result = _nombre_base_crudo("RAMS_Maya.xlsx")
        assert "rams" not in result.lower()


# ===========================================================================
# 6. Tests pair_files  (MVP logic)
# ===========================================================================

class TestPairFiles:

    def test_pair_basic(self):
        isa = ["ISA_Maya.xlsx", "ISA_Brent.xlsx"]
        rams = ["RAMS_Maya.xlsx", "RAMS_Brent.xlsx"]
        paired, u_isa, u_rams = pair_files(isa, rams)
        assert len(paired) == 2
        assert not u_isa
        assert not u_rams

    def test_unpaired_isa(self):
        isa = ["ISA_Maya.xlsx", "ISA_Extra.xlsx"]
        rams = ["RAMS_Maya.xlsx"]
        _, u_isa, u_rams = pair_files(isa, rams)
        assert "ISA_Extra.xlsx" in u_isa

    def test_unpaired_rams(self):
        isa = ["ISA_Maya.xlsx"]
        rams = ["RAMS_Maya.xlsx", "RAMS_Extra.xlsx"]
        _, u_isa, u_rams = pair_files(isa, rams)
        assert "RAMS_Extra.xlsx" in u_rams

    def test_structured_code(self):
        isa = ["GMX-2023-1_ISA.xlsx"]
        rams = ["GMX-2023-1_RAMS.xlsx"]
        paired, u_isa, u_rams = pair_files(isa, rams)
        assert len(paired) == 1
        assert not u_isa
        assert not u_rams

    def test_empty(self):
        paired, u_isa, u_rams = pair_files([], [])
        assert paired == {}


# ===========================================================================
# 7. Tests read_file
# ===========================================================================

class TestReadFile:

    def test_read_xlsx(self, simple_isa, isa_bytes):
        buf = io.BytesIO(isa_bytes)
        df = read_file(buf, "test.xlsx")
        assert df.shape == simple_isa.shape

    def test_read_csv_semicolon(self, simple_isa):
        csv = simple_isa.to_csv(index=False, sep=";", decimal=",").encode()
        df = read_file(io.BytesIO(csv), "test.csv")
        assert df.shape[0] == 3

    def test_unsupported_extension(self):
        with pytest.raises(ValueError, match="soportado"):
            read_file(io.BytesIO(b"data"), "file.xlsm")

    def test_corrupt_xlsx(self):
        with pytest.raises(ValueError):
            read_file(io.BytesIO(b"not an excel"), "corrupt.xlsx")


# ===========================================================================
# 8. Tests construir_umbrales  (MVP logic)
# ===========================================================================

class TestConstruirUmbrales:

    def test_basic(self, alias_prop):
        df = pd.DataFrame({
            "Propiedad": ["DENSIDAD", "DENSIDAD"],
            "Tipo": ["Reproductibilidad", "Admisible"],
            "150-200": [2.0, 1.5],
        })
        umbrales = construir_umbrales(df, alias_prop)
        # Debe conservar el mayor (2.0)
        assert umbrales.get(("DENSIDAD", "150-200")) == 2.0

    def test_no_propiedad_col_raises(self, alias_prop):
        df = pd.DataFrame({"Tipo": ["Repro"], "150-200": [1.0]})
        with pytest.raises(ValueError, match="'Propiedad'"):
            construir_umbrales(df, alias_prop)

    def test_no_tipo_col_raises(self, alias_prop):
        df = pd.DataFrame({"Propiedad": ["DENSIDAD"], "150-200": [1.0]})
        with pytest.raises(ValueError, match="Tipo"):
            construir_umbrales(df, alias_prop)

    def test_only_repro_accepted(self, alias_prop):
        df = pd.DataFrame({
            "Propiedad": ["DENSIDAD", "DENSIDAD"],
            "Tipo": ["Reproductibilidad", "Comentario"],
            "150-200": [2.0, 99.0],
        })
        umbrales = construir_umbrales(df, alias_prop)
        assert umbrales.get(("DENSIDAD", "150-200")) == 2.0

    def test_max_wins(self, alias_prop):
        df = pd.DataFrame({
            "Propiedad": ["AZUFRE", "AZUFRE"],
            "Tipo": ["Reproductibilidad", "Admisible"],
            "150-200": [0.05, 0.08],
        })
        umbrales = construir_umbrales(df, alias_prop)
        assert umbrales.get(("AZUFRE", "150-200")) == 0.08


# ===========================================================================
# 9. Tests clasificar_propiedad  (MVP logic — reglas completas)
# ===========================================================================

class TestClasificarPropiedad:

    @pytest.fixture
    def basic_umbrales(self):
        return {
            ("DENSIDAD", "150-200"): 2.0,
            ("VISCOSIDAD 50", "150-200"): 1.0,
            ("AZUFRE", "150-200"): 0.05,
            ("PESO", "150-200"): 1.0,
        }

    def test_verde(self, basic_umbrales):
        errores = {"150-200": 1.0}
        sem, _, _, _, _, _ = clasificar_propiedad(
            errores, "DENSIDAD", basic_umbrales, 0.1, 0.9, 0.3
        )
        assert sem == "VERDE"

    def test_amarillo(self, basic_umbrales):
        errores = {"150-200": 2.5}  # > 2.0 pero ≤ 2.0*(1.1)=2.2? No, es rojo. Usar 2.1
        errores = {"150-200": 2.1}
        sem, _, _, _, _, _ = clasificar_propiedad(
            errores, "VISCOSIDAD 50", basic_umbrales, 0.1, 0.9, 0.3
        )
        assert sem == "AMARILLO"

    def test_rojo(self, basic_umbrales):
        errores = {"150-200": 99.0}
        sem, _, _, _, _, _ = clasificar_propiedad(
            errores, "DENSIDAD", basic_umbrales, 0.1, 0.9, 0.3
        )
        assert sem == "ROJO"

    def test_rojo_absoluto_3x_umbral(self, basic_umbrales):
        """Error > 3× umbral → ROJO absoluto."""
        errores = {"150-200": 7.0}  # 3 * 2.0 = 6.0 < 7.0 → rojo absoluto
        sem, estados, _, _, _, _ = clasificar_propiedad(
            errores, "DENSIDAD", basic_umbrales, 0.1, 0.9, 0.3
        )
        assert sem == "ROJO"
        assert estados["150-200"] == "ROJO"

    def test_azufre_regla_especial_verde(self, basic_umbrales):
        """Azufre: ≤ 3× umbral → VERDE."""
        errores = {"150-200": 0.14}  # 3 * 0.05 = 0.15; 0.14 ≤ 0.15 → VERDE
        sem, _, _, _, _, _ = clasificar_propiedad(
            errores, "AZUFRE", basic_umbrales, 0.1, 0.9, 0.3
        )
        assert sem == "VERDE"

    def test_na_sin_umbral(self):
        errores = {"150-200": 1.0}
        sem, _, _, _, _, _ = clasificar_propiedad(
            errores, "SIN_UMBRAL_PROP", {}, 0.1, 0.9, 0.3
        )
        assert sem == "NA"

    def test_no_numerico_skipped(self, basic_umbrales):
        errores = {"150-200": None, "200-250": None}
        sem, _, _, _, _, _ = clasificar_propiedad(
            errores, "DENSIDAD", basic_umbrales, 0.1, 0.9, 0.3
        )
        assert sem == ""

    def test_peso_acumulado_fallback(self):
        """PESO ACUMULADO debe usar umbrales de PESO."""
        umbrales = {("PESO", "150-200"): 1.0}
        errores = {"150-200": 0.5}
        sem, _, _, _, _, _ = clasificar_propiedad(
            errores, "PESO ACUMULADO", umbrales, 0.1, 0.9, 0.3
        )
        assert sem == "VERDE"

    def test_corte_pesado_usa_tol_pesados(self, basic_umbrales):
        """Cortes pesados usan tol_pesados en lugar de tol estándar."""
        umbrales = {("DENSIDAD", "300-350"): 2.0}
        # tol_pesados=0.60 → umbral_amarillo = 2.0 * 1.60 = 3.20
        # error 2.8 > 2.0 (umbral) pero ≤ 3.20 → AMARILLO
        errores = {"300-350": 2.8}
        sem, _, _, _, _, _ = clasificar_propiedad(
            errores, "DENSIDAD", umbrales, 0.1, 0.9, 0.3, tol_pesados=0.6
        )
        assert sem == "AMARILLO"


# ===========================================================================
# 10. Tests _sem_global_por_crudo  (MVP logic)
# ===========================================================================

class TestSemGlobalPorCrudo:

    def test_todo_verde(self):
        resumen = {
            "DENSIDAD": {"Maya": "VERDE", "Brent": "VERDE"},
            "AZUFRE":   {"Maya": "VERDE", "Brent": "VERDE"},
        }
        out = _sem_global_por_crudo(resumen, 0.9, 0.3)
        assert out["Maya"] == "VERDE"
        assert out["Brent"] == "VERDE"

    def test_mayoria_rojos(self):
        resumen = {
            "DENSIDAD": {"Maya": "ROJO"},
            "AZUFRE":   {"Maya": "ROJO"},
            "VISCOSIDAD": {"Maya": "VERDE"},
        }
        out = _sem_global_por_crudo(resumen, 0.9, 0.3)
        # 2/3 rojos = 0.66 > 0.3 → ROJO
        assert out["Maya"] == "ROJO"

    def test_caso_amarillo(self):
        resumen = {
            "DENSIDAD": {"Maya": "VERDE"},
            "AZUFRE":   {"Maya": "AMARILLO"},
            "VISCOSIDAD": {"Maya": "VERDE"},
        }
        out = _sem_global_por_crudo(resumen, 0.9, 0.3)
        # 2/3 verdes = 0.66 < 0.9 → AMARILLO
        assert out["Maya"] == "AMARILLO"


# ===========================================================================
# 11. Tests calcular_errores_crudo_df  (MVP pipeline core)
# ===========================================================================

class TestCalcularErroresCrudoDf:

    def test_basic_output_shape(self, simple_isa, simple_rams, simple_umbrales, alias_prop):
        hoja_resumen = {}
        df_out, cortes, orden = calcular_errores_crudo_df(
            df_isa=simple_isa,
            df_rams=simple_rams,
            umbrales=simple_umbrales,
            alias_prop=alias_prop,
            tol=0.1,
            pct_ok_amarillo=0.9,
            pct_rojo_rojo=0.3,
            tol_pesados=0.6,
            hoja_resumen=hoja_resumen,
            crude_name="Maya",
        )
        assert "Semaforo" in df_out.columns
        assert "Propiedad" in df_out.columns
        assert "Corte_peor" in df_out.columns
        assert "Error_peor" in df_out.columns
        assert "Umbral_peor" in df_out.columns
        assert len(cortes) == 3  # 3 cortes

    def test_populates_resumen(self, simple_isa, simple_rams, simple_umbrales, alias_prop):
        hoja_resumen = {}
        calcular_errores_crudo_df(
            df_isa=simple_isa, df_rams=simple_rams,
            umbrales=simple_umbrales, alias_prop=alias_prop,
            tol=0.1, pct_ok_amarillo=0.9, pct_rojo_rojo=0.3, tol_pesados=0.6,
            hoja_resumen=hoja_resumen, crude_name="Maya",
        )
        # Al menos una propiedad debe estar en el resumen
        assert len(hoja_resumen) > 0
        for prop_dict in hoja_resumen.values():
            assert "Maya" in prop_dict

    def test_no_propiedad_col_raises(self, alias_prop):
        df = pd.DataFrame({"150-200": [1.0]})
        with pytest.raises(ValueError, match="Propiedad"):
            calcular_errores_crudo_df(
                df_isa=df, df_rams=df,
                umbrales={}, alias_prop=alias_prop,
                tol=0.1, pct_ok_amarillo=0.9, pct_rojo_rojo=0.3, tol_pesados=0.6,
                hoja_resumen={}, crude_name="test",
            )

    def test_errores_son_absolutos(self, alias_prop, simple_umbrales):
        """Todos los errores en las columnas de corte deben ser ≥ 0."""
        isa = pd.DataFrame({
            "Propiedad": ["Densidad"],
            "150-200": [850.0],
        })
        rams = pd.DataFrame({
            "Propiedad": ["Densidad"],
            "150-200": [852.0],
        })
        hoja_resumen = {}
        df_out, _, _ = calcular_errores_crudo_df(
            df_isa=isa, df_rams=rams,
            umbrales={("DENSIDAD", "150-200"): 5.0}, alias_prop=alias_prop,
            tol=0.1, pct_ok_amarillo=0.9, pct_rojo_rojo=0.3, tol_pesados=0.6,
            hoja_resumen=hoja_resumen, crude_name="test",
        )
        assert df_out["150-200"].iloc[0] == pytest.approx(2.0)


# ===========================================================================
# 12. Tests validate_params  (MVP validation)
# ===========================================================================

class TestValidateParams:

    def test_valid(self):
        validate_params(0.1, 0.6, 0.9, 0.3)  # sin excepción

    def test_negative_tol(self):
        with pytest.raises(ValueError, match="negativo"):
            validate_params(-0.1, 0.6, 0.9, 0.3)

    def test_pct_out_of_range(self):
        with pytest.raises(ValueError, match="0,1"):
            validate_params(0.1, 0.6, 1.5, 0.3)


# ===========================================================================
# 13. Tests build_summary_df  (MVP summary structure)
# ===========================================================================

class TestBuildSummaryDf:

    def test_global_row_first(self):
        resumen = {
            "DENSIDAD": {"Maya": "VERDE"},
            "AZUFRE":   {"Maya": "ROJO"},
        }
        df = _build_summary_df(resumen, ["DENSIDAD", "AZUFRE"], 0.9, 0.3)
        assert df.iloc[0]["Propiedad"] == "GLOBAL"

    def test_all_props_present(self):
        resumen = {
            "DENSIDAD": {"Maya": "VERDE"},
            "AZUFRE":   {"Maya": "ROJO"},
        }
        df = _build_summary_df(resumen, ["DENSIDAD", "AZUFRE"], 0.9, 0.3)
        propiedades = df["Propiedad"].tolist()
        assert "DENSIDAD" in propiedades
        assert "AZUFRE" in propiedades

    def test_crudo_columns(self):
        resumen = {
            "DENSIDAD": {"Maya": "VERDE", "Brent": "ROJO"},
        }
        df = _build_summary_df(resumen, ["DENSIDAD"], 0.9, 0.3)
        assert "Maya" in df.columns
        assert "Brent" in df.columns


# ===========================================================================
# 14. Tests build_excel  (MVP export structure)
# ===========================================================================

class TestBuildExcelMVP:

    def _make_result(self, alias_prop, simple_isa, simple_rams, simple_umbrales):
        hoja_resumen = {}
        df_out, cortes, orden = calcular_errores_crudo_df(
            df_isa=simple_isa, df_rams=simple_rams,
            umbrales=simple_umbrales, alias_prop=alias_prop,
            tol=0.1, pct_ok_amarillo=0.9, pct_rojo_rojo=0.3, tol_pesados=0.6,
            hoja_resumen=hoja_resumen, crude_name="Maya",
        )
        summary = _build_summary_df(hoja_resumen, orden, 0.9, 0.3)
        result = ValidationResult(
            paired_names=["Maya"],
            crudo_dataframes={"Maya": df_out},
            cortes_visibles={"Maya": cortes},
            resumen_raw=hoja_resumen,
            orden_propiedades=orden,
            summary=summary,
        )
        return result

    def test_returns_bytes(self, alias_prop, simple_isa, simple_rams, simple_umbrales):
        result = self._make_result(alias_prop, simple_isa, simple_rams, simple_umbrales)
        excel = build_excel(result)
        assert isinstance(excel, bytes)
        assert len(excel) > 0

    def test_has_resumen_sheet(self, alias_prop, simple_isa, simple_rams, simple_umbrales):
        import openpyxl
        result = self._make_result(alias_prop, simple_isa, simple_rams, simple_umbrales)
        excel = build_excel(result)
        wb = openpyxl.load_workbook(io.BytesIO(excel))
        assert "Resumen" in wb.sheetnames

    def test_has_crudo_sheet(self, alias_prop, simple_isa, simple_rams, simple_umbrales):
        import openpyxl
        result = self._make_result(alias_prop, simple_isa, simple_rams, simple_umbrales)
        excel = build_excel(result)
        wb = openpyxl.load_workbook(io.BytesIO(excel))
        assert "Maya" in wb.sheetnames

    def test_resumen_has_global_row(self, alias_prop, simple_isa, simple_rams, simple_umbrales):
        import openpyxl
        result = self._make_result(alias_prop, simple_isa, simple_rams, simple_umbrales)
        excel = build_excel(result)
        wb = openpyxl.load_workbook(io.BytesIO(excel))
        ws = wb["Resumen"]
        # Fila 2 debe ser GLOBAL (fila 1 = headers)
        assert ws.cell(2, 1).value == "GLOBAL"

    def test_crudo_sheet_has_semaforo_col(self, alias_prop, simple_isa, simple_rams, simple_umbrales):
        import openpyxl
        result = self._make_result(alias_prop, simple_isa, simple_rams, simple_umbrales)
        excel = build_excel(result)
        wb = openpyxl.load_workbook(io.BytesIO(excel))
        ws = wb["Maya"]
        headers = [ws.cell(1, j).value for j in range(1, ws.max_column + 1)]
        assert "Semaforo" in headers


# ===========================================================================
# 15. Tests run_validation (pipeline completo con matriz de umbrales)
# ===========================================================================

class TestRunValidation:

    def test_full_pipeline(self, isa_bytes, rams_bytes, matriz_bytes):
        isa_files = {"ISA_Maya.xlsx": io.BytesIO(isa_bytes)}
        rams_files = {"RAMS_Maya.xlsx": io.BytesIO(rams_bytes)}
        matriz = io.BytesIO(matriz_bytes)

        result = run_validation(
            isa_files=isa_files,
            rams_files=rams_files,
            matriz_file=matriz,
            matriz_filename="Errores_Cortes.xlsx",
        )
        assert result.has_results
        assert "Maya" in result.paired_names

    def test_pipeline_no_pairs(self, isa_bytes, rams_bytes, matriz_bytes):
        isa_files = {"ISA_Maya.xlsx": io.BytesIO(isa_bytes)}
        rams_files = {"RAMS_Brent.xlsx": io.BytesIO(rams_bytes)}
        matriz = io.BytesIO(matriz_bytes)

        result = run_validation(
            isa_files=isa_files,
            rams_files=rams_files,
            matriz_file=matriz,
            matriz_filename="Errores_Cortes.xlsx",
        )
        assert not result.has_results

    def test_pipeline_summary_has_global(self, isa_bytes, rams_bytes, matriz_bytes):
        isa_files = {"ISA_Maya.xlsx": io.BytesIO(isa_bytes)}
        rams_files = {"RAMS_Maya.xlsx": io.BytesIO(rams_bytes)}
        result = run_validation(
            isa_files=isa_files, rams_files=rams_files,
            matriz_file=io.BytesIO(matriz_bytes),
            matriz_filename="Errores_Cortes.xlsx",
        )
        assert "GLOBAL" in result.summary["Propiedad"].values

    def test_pipeline_crudo_dataframe_cols(self, isa_bytes, rams_bytes, matriz_bytes):
        """El df por crudo debe tener las columnas del MVP."""
        isa_files = {"ISA_Maya.xlsx": io.BytesIO(isa_bytes)}
        rams_files = {"RAMS_Maya.xlsx": io.BytesIO(rams_bytes)}
        result = run_validation(
            isa_files=isa_files, rams_files=rams_files,
            matriz_file=io.BytesIO(matriz_bytes),
            matriz_filename="Errores_Cortes.xlsx",
        )
        df = result.crudo_dataframes["Maya"]
        for col in ["Propiedad", "Semaforo", "Corte_peor", "Error_peor", "Umbral_peor"]:
            assert col in df.columns, f"Falta columna: {col}"

    def test_invalid_tol_raises(self, isa_bytes, rams_bytes, matriz_bytes):
        with pytest.raises(ValueError):
            run_validation(
                isa_files={"ISA_Maya.xlsx": io.BytesIO(isa_bytes)},
                rams_files={"RAMS_Maya.xlsx": io.BytesIO(rams_bytes)},
                matriz_file=io.BytesIO(matriz_bytes),
                matriz_filename="Errores_Cortes.xlsx",
                tol=-0.1,
            )


# ===========================================================================
# 16. Tests de compatibilidad  (tests existentes que deben seguir pasando)
# ===========================================================================

class TestBackwardsCompat:

    def test_canonize_name_alias(self):
        """canonize_name es alias de _nombre_base_crudo."""
        assert canonize_name("ISA_Maya.xlsx") == _nombre_base_crudo("ISA_Maya.xlsx")

    def test_validate_thresholds_valid(self):
        config = ThresholdConfig(default_green=1.0, default_yellow=3.0)
        validate_thresholds(config)

    def test_validate_thresholds_invalid(self):
        config = ThresholdConfig(default_green=5.0, default_yellow=3.0)
        with pytest.raises(ValueError, match="globales"):
            validate_thresholds(config)

    def test_validate_thresholds_per_prop(self):
        config = ThresholdConfig(
            default_green=1.0,
            default_yellow=3.0,
            thresholds={"densidad": (5.0, 2.0)},
        )
        with pytest.raises(ValueError, match="densidad"):
            validate_thresholds(config)

    def test_constants_present(self):
        assert "VERDE" in SEMAFORO_COLORS
        assert "AMARILLO" in SEMAFORO_COLORS
        assert "ROJO" in SEMAFORO_COLORS
        assert ".xlsx" in SUPPORTED_EXTENSIONS
        assert ".csv" in SUPPORTED_EXTENSIONS

    def test_default_constants(self):
        assert DEFAULT_TOL == 0.10
        assert DEFAULT_TOL_PESADOS == 0.60
        assert DEFAULT_PCT_OK_AMARILLO == 0.90
        assert DEFAULT_PCT_ROJO_ROJO == 0.30

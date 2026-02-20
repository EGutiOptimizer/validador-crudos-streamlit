"""
tests/test_validator_core.py
============================
Tests unitarios para la lógica core del validador.
Ejecutar con: pytest tests/ -v
"""
from __future__ import annotations

import io
import pytest
import pandas as pd
import numpy as np

from core.models import ThresholdConfig, ValidationResult
from core.validator_core import (
    canonize_name,
    pair_files,
    read_file,
    compute_errors,
    classify_semaforo,
    classify_matrix,
    build_summary,
    validate_thresholds,
    build_excel,
    run_validation,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def simple_isa() -> pd.DataFrame:
    """DataFrame ISA de referencia con 3 cortes y 3 propiedades."""
    return pd.DataFrame({
        "corte": [10, 20, 30],
        "densidad": [850.0, 860.0, 870.0],
        "viscosidad": [5.0, 6.0, 7.0],
        "gravedad_api": [30.0, 28.0, 26.0],
    })


@pytest.fixture
def simple_rams() -> pd.DataFrame:
    """DataFrame RAMS con pequeñas desviaciones respecto a ISA."""
    return pd.DataFrame({
        "corte": [10, 20, 30],
        "densidad": [851.0, 858.5, 872.0],   # errores: 1.0, 1.5, 2.0
        "viscosidad": [5.5, 6.0, 6.5],        # errores: 0.5, 0.0, 0.5
        "gravedad_api": [29.5, 31.0, 24.0],   # errores: 0.5, 3.0, 2.0
    })


@pytest.fixture
def default_config() -> ThresholdConfig:
    return ThresholdConfig(default_green=1.0, default_yellow=3.0)


@pytest.fixture
def isa_bytes(simple_isa) -> bytes:
    """ISA como bytes de archivo Excel."""
    buf = io.BytesIO()
    simple_isa.to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def rams_bytes(simple_rams) -> bytes:
    """RAMS como bytes de archivo Excel."""
    buf = io.BytesIO()
    simple_rams.to_excel(buf, index=False)
    return buf.getvalue()


# ===========================================================================
# 1. Tests canonize_name
# ===========================================================================

class TestCanonizeName:

    @pytest.mark.parametrize("input_name,expected", [
        ("ISA_Crudo_Maya.xlsx",     "crudomaya"),
        ("RAMS-Crudo_Maya.xlsx",    "crudomaya"),
        ("crudo_maya_ISA.xlsx",     "crudomaya"),
        ("crudo_maya_RAMS.csv",     "crudomaya"),
        ("Crudo Máya.xlsx",         "crudomaya"),    # acentos
        ("CRUDO_MAYA.xlsx",         "crudomaya"),    # mayúsculas
        ("isa-crudo-maya.xls",      "crudomaya"),
        ("rams_crudo_maya.xls",     "crudomaya"),
        ("Crudo-Maya 2024.xlsx",    "crudomaya2024"),
        ("ISA.xlsx",                ""),             # solo prefijo → vacío
    ])
    def test_canonize_parametrized(self, input_name, expected):
        assert canonize_name(input_name) == expected

    def test_canonize_removes_extension(self):
        assert canonize_name("archivo.csv") == "archivo"

    def test_canonize_empty_string(self):
        assert canonize_name("") == ""

    def test_canonize_special_chars(self):
        # Caracteres especiales → eliminados
        result = canonize_name("crudo@maya#1.xlsx")
        assert result == "crudomaya1"


# ===========================================================================
# 2. Tests pair_files
# ===========================================================================

class TestPairFiles:

    def test_pair_basic(self):
        isa = ["ISA_Maya.xlsx", "ISA_Brent.xlsx"]
        rams = ["RAMS_Maya.xlsx", "RAMS_Brent.xlsx"]
        paired, unpaired_isa, unpaired_rams = pair_files(isa, rams)
        assert len(paired) == 2
        assert not unpaired_isa
        assert not unpaired_rams

    def test_pair_unpaired_isa(self):
        isa = ["ISA_Maya.xlsx", "ISA_Extra.xlsx"]
        rams = ["RAMS_Maya.xlsx"]
        _, unpaired_isa, unpaired_rams = pair_files(isa, rams)
        assert len(unpaired_isa) == 1
        assert "ISA_Extra.xlsx" in unpaired_isa

    def test_pair_unpaired_rams(self):
        isa = ["ISA_Maya.xlsx"]
        rams = ["RAMS_Maya.xlsx", "RAMS_Extra.xlsx"]
        _, unpaired_isa, unpaired_rams = pair_files(isa, rams)
        assert len(unpaired_rams) == 1
        assert "RAMS_Extra.xlsx" in unpaired_rams

    def test_pair_empty_inputs(self):
        paired, u_isa, u_rams = pair_files([], [])
        assert paired == {}
        assert u_isa == []
        assert u_rams == []

    def test_pair_case_insensitive(self):
        isa = ["ISA_Maya.xlsx"]
        rams = ["RAMS_MAYA.xlsx"]  # mayúsculas
        paired, u_isa, u_rams = pair_files(isa, rams)
        assert len(paired) == 1
        assert not u_isa
        assert not u_rams


# ===========================================================================
# 3. Tests read_file
# ===========================================================================

class TestReadFile:

    def test_read_xlsx(self, simple_isa, isa_bytes):
        buf = io.BytesIO(isa_bytes)
        df = read_file(buf, "test_isa.xlsx")
        assert df.shape == simple_isa.shape
        assert list(df.columns) == list(simple_isa.columns)

    def test_read_csv_semicolon(self, simple_isa):
        csv_content = simple_isa.to_csv(index=False, sep=";", decimal=",").encode()
        buf = io.BytesIO(csv_content)
        df = read_file(buf, "test.csv")
        assert df.shape[0] == 3

    def test_read_csv_comma(self, simple_isa):
        csv_content = simple_isa.to_csv(index=False, sep=",").encode()
        buf = io.BytesIO(csv_content)
        df = read_file(buf, "test.csv")
        assert df.shape[0] == 3

    def test_unsupported_extension(self):
        buf = io.BytesIO(b"datos")
        with pytest.raises(ValueError, match="Formato no soportado"):
            read_file(buf, "archivo.xlsm")

    def test_corrupt_file(self):
        buf = io.BytesIO(b"esto no es un excel")
        with pytest.raises(ValueError):
            read_file(buf, "corrupto.xlsx")


# ===========================================================================
# 4. Tests compute_errors
# ===========================================================================

class TestComputeErrors:

    def test_errors_shape(self, simple_isa, simple_rams):
        errors = compute_errors(simple_isa, simple_rams, "corte")
        assert errors.shape == (3, 3)  # 3 cortes × 3 propiedades numéricas

    def test_errors_values(self, simple_isa, simple_rams):
        errors = compute_errors(
            simple_isa, simple_rams, "corte", prop_cols=["densidad"]
        )
        expected = [1.0, 1.5, 2.0]
        assert list(errors["densidad"].round(4)) == expected

    def test_errors_all_zero(self, simple_isa):
        """Si ISA == RAMS todos los errores deben ser 0."""
        errors = compute_errors(simple_isa, simple_isa.copy(), "corte")
        assert (errors == 0).all().all()

    def test_errors_missing_rams_row(self, simple_isa, simple_rams):
        """Corte faltante en RAMS → NaN en error."""
        rams_short = simple_rams.iloc[:2].copy()  # falta corte 30
        errors = compute_errors(simple_isa, rams_short, "corte", prop_cols=["densidad"])
        assert pd.isna(errors["densidad"].iloc[-1])

    def test_errors_missing_key_col(self, simple_isa, simple_rams):
        with pytest.raises(ValueError, match="no encontrada"):
            compute_errors(simple_isa, simple_rams, "columna_inexistente")

    def test_errors_no_numeric_cols(self):
        df = pd.DataFrame({"corte": [1, 2], "texto": ["a", "b"]})
        with pytest.raises(ValueError, match="numéricas"):
            compute_errors(df, df.copy(), "corte")


# ===========================================================================
# 5. Tests classify_semaforo
# ===========================================================================

class TestClassifySemaforo:

    @pytest.mark.parametrize("error,green,yellow,expected", [
        (0.0,  1.0, 3.0, "verde"),
        (1.0,  1.0, 3.0, "verde"),    # límite exacto verde (inclusivo)
        (1.5,  1.0, 3.0, "amarillo"),
        (3.0,  1.0, 3.0, "amarillo"), # límite exacto amarillo (inclusivo)
        (3.01, 1.0, 3.0, "rojo"),
        (100,  1.0, 3.0, "rojo"),
        (0.0,  0.0, 1.0, "verde"),    # umbral verde en 0
    ])
    def test_classify_parametrized(self, error, green, yellow, expected):
        assert classify_semaforo(error, green, yellow) == expected

    def test_classify_nan_is_rojo(self):
        assert classify_semaforo(float("nan"), 1.0, 3.0) == "rojo"

    def test_classify_invalid_thresholds(self):
        with pytest.raises(ValueError):
            classify_semaforo(1.0, green=3.0, yellow=1.0)  # verde > amarillo

    def test_classify_equal_thresholds(self):
        with pytest.raises(ValueError):
            classify_semaforo(1.0, green=2.0, yellow=2.0)  # igual no válido


# ===========================================================================
# 6. Tests classify_matrix
# ===========================================================================

class TestClassifyMatrix:

    def test_matrix_shape(self, simple_isa, simple_rams, default_config):
        errors = compute_errors(simple_isa, simple_rams, "corte")
        semaforo = classify_matrix(errors, default_config)
        assert semaforo.shape == errors.shape

    def test_matrix_values_valid(self, simple_isa, simple_rams, default_config):
        errors = compute_errors(simple_isa, simple_rams, "corte")
        semaforo = classify_matrix(errors, default_config)
        valid = {"verde", "amarillo", "rojo"}
        for val in semaforo.values.flatten():
            assert val in valid

    def test_matrix_custom_thresholds(self, simple_isa, simple_rams):
        """Con umbrales muy estrictos todo debería ser rojo."""
        errors = compute_errors(simple_isa, simple_rams, "corte")
        strict_config = ThresholdConfig(default_green=0.001, default_yellow=0.01)
        semaforo = classify_matrix(errors, strict_config)
        # La mayoría de errores > 0.01 → rojo
        assert (semaforo == "rojo").values.sum() > 0


# ===========================================================================
# 7. Tests build_summary
# ===========================================================================

class TestBuildSummary:

    def test_summary_columns(self, simple_isa, simple_rams, default_config):
        errors = compute_errors(simple_isa, simple_rams, "corte")
        semaforo = classify_matrix(errors, default_config)
        summary = build_summary({"maya": semaforo})
        expected_cols = {"crudo", "verde_%", "amarillo_%", "rojo_%", "total_celdas", "estado_global"}
        assert expected_cols.issubset(set(summary.columns))

    def test_summary_percentages_sum(self, simple_isa, simple_rams, default_config):
        errors = compute_errors(simple_isa, simple_rams, "corte")
        semaforo = classify_matrix(errors, default_config)
        summary = build_summary({"maya": semaforo})
        row = summary.iloc[0]
        total = row["verde_%"] + row["amarillo_%"] + row["rojo_%"]
        assert abs(total - 100.0) < 0.2  # tolerancia por redondeo

    def test_summary_all_verde(self, simple_isa):
        """Si todos los errores son 0, el estado global debe ser verde."""
        errors = compute_errors(simple_isa, simple_isa.copy(), "corte")
        config = ThresholdConfig(default_green=1.0, default_yellow=3.0)
        semaforo = classify_matrix(errors, config)
        summary = build_summary({"ref": semaforo})
        assert summary.iloc[0]["estado_global"] == "verde"


# ===========================================================================
# 8. Tests validate_thresholds
# ===========================================================================

class TestValidateThresholds:

    def test_valid_config(self):
        config = ThresholdConfig(default_green=1.0, default_yellow=3.0)
        validate_thresholds(config)  # no debe lanzar

    def test_invalid_global(self):
        config = ThresholdConfig(default_green=5.0, default_yellow=3.0)
        with pytest.raises(ValueError, match="globales inválidos"):
            validate_thresholds(config)

    def test_invalid_per_property(self):
        config = ThresholdConfig(
            default_green=1.0,
            default_yellow=3.0,
            thresholds={"densidad": (5.0, 2.0)}  # verde > amarillo
        )
        with pytest.raises(ValueError, match="densidad"):
            validate_thresholds(config)


# ===========================================================================
# 9. Tests build_excel
# ===========================================================================

class TestBuildExcel:

    def test_returns_bytes(self, simple_isa, simple_rams, default_config):
        errors = compute_errors(simple_isa, simple_rams, "corte")
        semaforo = classify_matrix(errors, default_config)
        from core.models import ValidationResult
        import pandas as pd
        result = ValidationResult(
            paired_names=["maya"],
            error_matrices={"maya": errors},
            semaforo_matrices={"maya": semaforo},
            summary=build_summary({"maya": semaforo}),
        )
        excel_bytes = build_excel(result, default_config)
        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

    def test_excel_has_sheets(self, simple_isa, simple_rams, default_config):
        import openpyxl
        errors = compute_errors(simple_isa, simple_rams, "corte")
        semaforo = classify_matrix(errors, default_config)
        result = ValidationResult(
            paired_names=["maya"],
            error_matrices={"maya": errors},
            semaforo_matrices={"maya": semaforo},
            summary=build_summary({"maya": semaforo}),
        )
        excel_bytes = build_excel(result, default_config)
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        assert "Resumen" in wb.sheetnames
        assert "maya" in wb.sheetnames
        assert "Leyenda" in wb.sheetnames


# ===========================================================================
# 10. Test integración pipeline completo
# ===========================================================================

class TestRunValidation:

    def test_full_pipeline(self, isa_bytes, rams_bytes, default_config):
        isa_files = {"ISA_Maya.xlsx": io.BytesIO(isa_bytes)}
        rams_files = {"RAMS_Maya.xlsx": io.BytesIO(rams_bytes)}
        result = run_validation(isa_files, rams_files, "corte", default_config)
        assert result.has_results
        assert "maya" in result.paired_names
        assert not result.unpaired_isa
        assert not result.unpaired_rams

    def test_pipeline_no_pairs(self, isa_bytes, rams_bytes, default_config):
        isa_files = {"ISA_Maya.xlsx": io.BytesIO(isa_bytes)}
        rams_files = {"RAMS_Brent.xlsx": io.BytesIO(rams_bytes)}  # sin par
        result = run_validation(isa_files, rams_files, "corte", default_config)
        assert not result.has_results
        assert result.unpaired_isa
        assert result.unpaired_rams

    def test_pipeline_invalid_key_col(self, isa_bytes, rams_bytes):
        config = ThresholdConfig(default_green=1.0, default_yellow=3.0)
        isa_files = {"ISA_Maya.xlsx": io.BytesIO(isa_bytes)}
        rams_files = {"RAMS_Maya.xlsx": io.BytesIO(rams_bytes)}
        # Columna que no existe → el par se reporta como error, no falla todo
        result = run_validation(isa_files, rams_files, "columna_inexistente", config)
        assert not result.has_results
        # Se reporta como ISA con error
        assert any("ERROR" in f for f in result.unpaired_isa)

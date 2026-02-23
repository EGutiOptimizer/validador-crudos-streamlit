"""
core/models.py
==============
Modelos de datos puros para el validador de crudos RAMS vs ISA.

Sin dependencias de Streamlit ni de validator_core — 100% testeable en aislamiento.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# ThresholdConfig  (mantenida para compatibilidad con tests existentes)
# ---------------------------------------------------------------------------

@dataclass
class ThresholdConfig:
    """Configuración de umbrales simple (para tests de compatibilidad).

    En el pipeline completo se usa la matriz de umbrales del MVP.
    """
    default_green: float = 1.0
    default_yellow: float = 3.0
    thresholds: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def get_thresholds(self, prop: str) -> Tuple[float, float]:
        if prop in self.thresholds:
            return self.thresholds[prop]
        return self.default_green, self.default_yellow


# ---------------------------------------------------------------------------
# ValidationResult  (extendido para paridad con el MVP)
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """
    Resultado completo de una validación RAMS vs ISA.

    Atributos principales (nuevos, paridad con MVP):
        crudo_dataframes:   nombre_crudo → DataFrame con columnas
                            Propiedad | Semaforo | Corte_peor | Error_peor | Umbral_peor | [cortes...]
        cortes_visibles:    nombre_crudo → lista de nombres de columnas de corte (orden ISA)
        resumen_raw:        Dict[prop_canon → Dict[crude_name → semáforo]]
        orden_propiedades:  Lista de props en el orden del primer ISA procesado
        pct_ok_amarillo:    Parámetro guardado para exportación
        pct_rojo_rojo:      Parámetro guardado para exportación

    Atributos heredados (compatibilidad):
        paired_names:       Nombres de crudos procesados correctamente
        summary:            DataFrame Resumen (Propiedad × crudos + fila GLOBAL)
        unpaired_isa:       Archivos ISA sin par
        unpaired_rams:      Archivos RAMS sin par ISA
    """
    # Core pipeline output
    paired_names: List[str] = field(default_factory=list)
    crudo_dataframes: Dict[str, pd.DataFrame] = field(default_factory=dict)
    cortes_visibles: Dict[str, List[str]] = field(default_factory=dict)
    resumen_raw: Dict[str, Dict[str, str]] = field(default_factory=dict)
    orden_propiedades: List[str] = field(default_factory=list)
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Parámetros (para exportación y display)
    pct_ok_amarillo: float = 0.90
    pct_rojo_rojo: float = 0.30

    # Unpaired
    unpaired_isa: List[str] = field(default_factory=list)
    unpaired_rams: List[str] = field(default_factory=list)

    # Compatibilidad con UI antigua (mantenidos como alias)
    @property
    def error_matrices(self) -> Dict[str, pd.DataFrame]:
        """Alias: devuelve las columnas numéricas del df_out para cada crudo."""
        out: Dict[str, pd.DataFrame] = {}
        for name, df in self.crudo_dataframes.items():
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            if numeric_cols:
                out[name] = df[numeric_cols]
        return out

    @property
    def semaforo_matrices(self) -> Dict[str, pd.DataFrame]:
        """Alias: para compatibilidad, devuelve la columna Semaforo indexada por Propiedad."""
        out: Dict[str, pd.DataFrame] = {}
        for name, df in self.crudo_dataframes.items():
            if "Propiedad" in df.columns and "Semaforo" in df.columns:
                out[name] = df.set_index("Propiedad")[["Semaforo"]]
        return out

    @property
    def has_results(self) -> bool:
        return len(self.paired_names) > 0

    @property
    def total_pairs(self) -> int:
        return len(self.paired_names)

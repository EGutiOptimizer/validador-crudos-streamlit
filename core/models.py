"""
core/models.py
==============
Modelos de datos puros para el validador de crudos RAMS vs ISA.

Sin dependencias de Streamlit ni de validator_core — 100% testeable en
aislamiento. Todos los demás módulos importan desde aquí.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


# ---------------------------------------------------------------------------
# ThresholdConfig
# ---------------------------------------------------------------------------

@dataclass
class ThresholdConfig:
    """Configuración de umbrales de clasificación semáforo.

    Attributes:
        default_green:  Error máximo (inclusivo) para clasificar como verde.
        default_yellow: Error máximo (inclusivo) para clasificar como amarillo.
                        Cualquier valor por encima → rojo.
        thresholds:     Mapa propiedad → (umbral_verde, umbral_amarillo).
                        Si una propiedad no aparece aquí se usan los globales.
    """
    default_green: float = 1.0
    default_yellow: float = 3.0
    thresholds: dict[str, tuple[float, float]] = field(default_factory=dict)

    def get_thresholds(self, prop: str) -> tuple[float, float]:
        """Devuelve (umbral_verde, umbral_amarillo) para una propiedad dada.

        Usa el umbral específico de la propiedad si existe; en caso contrario
        devuelve los umbrales globales.

        Args:
            prop: Nombre de la propiedad / columna.

        Returns:
            Tupla (verde, amarillo).
        """
        if prop in self.thresholds:
            return self.thresholds[prop]
        return self.default_green, self.default_yellow


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Resultado completo de una validación RAMS vs ISA.

    Attributes:
        paired_names:      Nombres canónicos de los pares procesados con éxito.
        error_matrices:    nombre_crudo → DataFrame de errores absolutos |ISA-RAMS|.
        semaforo_matrices: nombre_crudo → DataFrame de clasificaciones ('verde' / 'amarillo' / 'rojo').
        summary:           Resumen global por crudo (verde_%, amarillo_%, rojo_%, estado_global).
        unpaired_isa:      Archivos ISA para los que no se encontró par RAMS.
        unpaired_rams:     Archivos RAMS para los que no se encontró par ISA.
    """
    paired_names: list[str] = field(default_factory=list)
    error_matrices: dict[str, pd.DataFrame] = field(default_factory=dict)
    semaforo_matrices: dict[str, pd.DataFrame] = field(default_factory=dict)
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    unpaired_isa: list[str] = field(default_factory=list)
    unpaired_rams: list[str] = field(default_factory=list)

    @property
    def has_results(self) -> bool:
        """True si hay al menos un par procesado correctamente."""
        return len(self.paired_names) > 0

    @property
    def total_pairs(self) -> int:
        """Número de pares procesados correctamente."""
        return len(self.paired_names)

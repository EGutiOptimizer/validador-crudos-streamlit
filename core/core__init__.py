"""
core/__init__.py
================
Paquete de lógica de negocio pura del Validador de Crudos.

Expone los símbolos principales para que otros módulos puedan importar
directamente desde 'core' si lo prefieren, aunque los imports explícitos
desde 'core.models' y 'core.validator_core' también funcionan.
"""
from core.models import ThresholdConfig, ValidationResult
from core.validator_core import (
    run_validation,
    build_excel,
    read_file,
    canonize_name,
    pair_files,
    compute_errors,
    classify_semaforo,
    classify_matrix,
    build_summary,
    validate_thresholds,
    SEMAFORO_LABELS,
    SEMAFORO_COLORS,
    SUPPORTED_EXTENSIONS,
)

__all__ = [
    # Modelos
    "ThresholdConfig",
    "ValidationResult",
    # Pipeline
    "run_validation",
    "build_excel",
    "read_file",
    # Utilidades
    "canonize_name",
    "pair_files",
    "compute_errors",
    "classify_semaforo",
    "classify_matrix",
    "build_summary",
    "validate_thresholds",
    # Constantes
    "SEMAFORO_LABELS",
    "SEMAFORO_COLORS",
    "SUPPORTED_EXTENSIONS",
]

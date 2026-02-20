"""Core: lógica de validación RAMS vs ISA. Sin dependencias de Streamlit."""
from core.models import ValidationResult, ThresholdConfig
from core.validator_core import (
    canonize_name,
    pair_files,
    read_file,
    compute_errors,
    classify_semaforo,
    classify_matrix,
    build_summary,
    run_validation,
    build_excel,
)

__all__ = [
    "ValidationResult",
    "ThresholdConfig",
    "canonize_name",
    "pair_files",
    "read_file",
    "compute_errors",
    "classify_semaforo",
    "classify_matrix",
    "build_summary",
    "run_validation",
    "build_excel",
]

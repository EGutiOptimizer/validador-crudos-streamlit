"""
conftest.py — Configuración global de pytest.
Asegura que el directorio raíz esté en sys.path para imports de core/ y ui/.
"""
import sys
import os

# Agregar raíz del proyecto a sys.path para que `import core` funcione en tests
sys.path.insert(0, os.path.dirname(__file__))

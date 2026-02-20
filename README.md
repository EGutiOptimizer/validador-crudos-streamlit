# 🛢️ Validador de Crudos RAMS vs ISA

> Herramienta web para validar predicciones de modelos **RAMS** contra mediciones de laboratorio **ISA**, calculando errores absolutos por propiedad y corte de destilación, clasificando resultados mediante un sistema de semáforos y exportando informes a Excel — todo desde el navegador, sin instalar Python.

---

## Índice

1. [¿Qué es y para qué sirve?](#1-qué-es-y-para-qué-sirve)
2. [Conceptos clave del dominio](#2-conceptos-clave-del-dominio)
3. [Arquitectura y estructura del proyecto](#3-arquitectura-y-estructura-del-proyecto)
4. [Dependencias](#4-dependencias)
5. [Diagrama de flujo completo](#5-diagrama-de-flujo-completo)
6. [Objetivo y funcionamiento de cada archivo](#6-objetivo-y-funcionamiento-de-cada-archivo)
7. [Cómo funciona por dentro — lógica detallada](#7-cómo-funciona-por-dentro--lógica-detallada)
8. [Formatos de archivo soportados](#8-formatos-de-archivo-soportados)
9. [Cómo se usa — guía paso a paso](#9-cómo-se-usa--guía-paso-a-paso)
10. [Instalación y ejecución local](#10-instalación-y-ejecución-local)
11. [Despliegue en Streamlit Cloud](#11-despliegue-en-streamlit-cloud)
12. [Configuración de secrets](#12-configuración-de-secrets)
13. [Tests unitarios](#13-tests-unitarios)
14. [Publicar cambios (VS Code → GitHub → Cloud)](#14-publicar-cambios-vs-code--github--cloud)
15. [Preguntas frecuentes y resolución de problemas](#15-preguntas-frecuentes-y-resolución-de-problemas)
16. [Licencia](#16-licencia)

---

## 1. ¿Qué es y para qué sirve?

El **Validador de Crudos RAMS/ISA** es una aplicación web desarrollada con [Streamlit](https://streamlit.io) que automatiza la comparación entre dos fuentes de datos de propiedades fisicoquímicas de crudos de petróleo:

| Fuente | Qué es | Rol |
|--------|--------|-----|
| **ISA** | Mediciones de laboratorio (valores de referencia) | Referencia absoluta de verdad |
| **RAMS** | Predicciones de un modelo predictivo | Valores a validar |

### Problema que resuelve

Los equipos de modelado predictivo de crudos necesitan saber si sus modelos RAMS reproducen fielmente las propiedades medidas en laboratorio (ISA). Sin esta herramienta, esa comparación se hacía manualmente en Excel, archivo por archivo, propiedad por propiedad — un proceso lento, propenso a errores y difícil de replicar.

### Qué hace la herramienta

- **Empareja** automáticamente archivos ISA y RAMS por nombre de crudo, con tolerancia a prefijos/sufijos y variaciones de nomenclatura.
- **Calcula** el error absoluto `|ISA - RAMS|` para cada propiedad y cada corte de destilación.
- **Clasifica** cada propiedad como 🟢 VERDE / 🟡 AMARILLO / 🔴 ROJO según umbrales configurables (extraídos de una matriz de reproductibilidad).
- **Genera** un resumen global por crudo y un detalle por propiedad, visualizables directamente en el navegador.
- **Exporta** un informe Excel con formato condicional de color listo para compartir.

### Usuarios objetivo

- **Validadores de crudos**: personas responsables de evaluar la calidad de los modelos predictivos.
- **Desarrolladores de modelos RAMS**: ingenieros que necesitan feedback cuantitativo sobre la precisión de sus predicciones.

---

## 2. Conceptos clave del dominio

### Crudos y cortes de destilación

El petróleo crudo se caracteriza mediante **destilación fraccionada**: se calienta y se recogen fracciones a distintos rangos de temperatura (los "cortes"). Cada corte tiene propiedades fisicoquímicas propias.

Ejemplos de cortes:
- `150-200` → fracción que destila entre 150 °C y 200 °C
- `300+` → fracción que destila por encima de 300 °C (corte "pesado")
- `C6-C10` → cortes 6 al 10

### Propiedades

Para cada corte se miden propiedades como densidad, viscosidad, contenido en azufre, punto de vertido, PIONA (parafinas, isoparafinas, olefinas, naftenos, aromáticos), etc.

### Umbrales de reproductibilidad

La matriz de umbrales define, para cada combinación propiedad × corte, cuánto puede diferir una medición RAMS de la ISA antes de considerarse un error inaceptable. Estos umbrales provienen de normas de ensayo (ASTM, ISO) o de acuerdos internos de calidad.

### Semáforo

La clasificación del error usa un sistema de tres niveles:

| Color | Criterio | Significado |
|-------|----------|-------------|
| 🟢 **VERDE** | Error dentro del umbral (o hasta 3× para Azufre/Densidad) | El modelo reproduce bien el laboratorio |
| 🟡 **AMARILLO** | Error ligeramente por encima del umbral (dentro de la tolerancia) | Aceptable pero a vigilar |
| 🔴 **ROJO** | Error fuera de la tolerancia o ausencia de dato | El modelo necesita revisión |

---

## 3. Arquitectura y estructura del proyecto

### Principio de diseño: separación estricta de capas

```
┌─────────────────────────────────────┐
│           CAPA UI (Streamlit)       │
│   app.py  +  ui/styling.py          │
│   - Recibe inputs del usuario       │
│   - Muestra resultados              │
│   - NO contiene lógica de negocio   │
└──────────────┬──────────────────────┘
               │ llama a
┌──────────────▼──────────────────────┐
│         CAPA CORE (Python puro)     │
│   core/validator_core.py            │
│   - Sin imports de Streamlit        │
│   - 100% testeable en aislamiento   │
│   - Toda la lógica de validación    │
└─────────────────────────────────────┘
```

### Estructura de archivos

```
validador-crudos-streamlit/
│
├── app.py                        ← Entrypoint Streamlit (punto de entrada)
│
├── core/
│   ├── __init__.py               ← Paquete Python (necesario para imports en Cloud)
│   └── validator_core.py         ← Toda la lógica de negocio (720+ líneas)
│
├── ui/
│   ├── __init__.py               ← Paquete Python
│   └── styling.py                ← Componentes de color y presentación
│
├── tests/
│   ├── __init__.py
│   └── test_validator_core.py    ← 42 tests unitarios del core
│
├── .streamlit/
│   ├── config.toml               ← Tema visual de la app
│   └── secrets.toml.example      ← Plantilla de secrets (el real va en .gitignore)
│
├── conftest.py                   ← Configuración de pytest (sys.path)
├── requirements.txt              ← Dependencias Python para Streamlit Cloud
├── .gitignore                    ← Excluye secrets, datos reales, __pycache__
└── README.md                     ← Este archivo
```

---

## 4. Dependencias

### Dependencias de producción (`requirements.txt`)

|   Paquete   |    Versión     | Para qué se usa |
|-------------|----------------|-----------------|
| `streamlit` | `>=1.32, <2.0` | Framework de la interfaz web; botones, uploads, tablas, descarga |
| `pandas`    | `>=2.0, <3.0`  | Manipulación de DataFrames; lectura de archivos, cálculo de errores |
| `openpyxl`  | `>=3.1, <4.0`  | Lectura y **escritura** de `.xlsx` con estilos y formato condicional |
| `xlrd`      | `>=2.0.1, <3.0`| Lectura de archivos `.xls` (formato Excel antiguo). ⚠️ NO soporta `.xlsx` |
| `pyxlsb`    | `>=1.0.10`     | Lectura de archivos `.xlsb` (Excel binario) |

### Dependencias de desarrollo (no van a Cloud)

| Paquete | Para qué |
|---------|----------|
| `pytest`| Ejecutar la suite de tests unitarios |

### Árbol de dependencias internas

```
app.py
 ├── core.validator_core
 │    ├── io (stdlib)
 │    ├── logging (stdlib)
 │    ├── os, re, unicodedata (stdlib)
 │    ├── pandas
 │    └── openpyxl
 └── ui.styling
      └── pandas
```

### Por qué cada engine de Excel tiene su rol

```
Extensión  →  Engine correcto
.xlsx      →  openpyxl   (único que soporta .xlsx moderno)
.xls       →  xlrd       (formato Excel 97-2003; xlrd ≥ 2.0 NO abre .xlsx)
.xlsb      →  pyxlsb     (formato binario comprimido)
.csv       →  pandas     (auto-detección de separador: ; , \t |)
```

---

## 5. Diagrama de flujo completo

```
USUARIO (navegador)
        │
        │  Sube archivos en el sidebar
        ▼
┌───────────────────────────────────────────────────────────────┐
│  app.py — Sidebar                                             │
│                                                               │
│  [1] Matriz de umbrales (.xlsx/.xls)                          │
│  [2] Archivos ISA (múltiples: .xlsx/.xls/.csv)                │
│  [3] Archivos RAMS (múltiples: .xlsx/.xls/.csv)               │
│  [4] Parámetros:                                              │
│       • tolerancia estándar (ej. 0.10)                        │
│       • tolerancia cortes pesados (ej. 0.60)                  │
│       • % mínimo verdes para VERDE global                     │
│       • % máximo rojos para ROJO global                       │
│  [5] Botón "Validar ahora"                                    │
└───────────────────┬───────────────────────────────────────────┘
                    │ session_state persiste archivos entre reruns
                    ▼
┌───────────────────────────────────────────────────────────────┐
│  core/validator_core.py — run_validation_in_memory()          │
│                                                               │
│  PASO 1: Leer matriz de umbrales                              │
│    leer_tabla_errores_filelike(matriz_bytes, matriz_name)     │
│    construir_umbrales(df_matriz, alias_prop)                  │
│    → Dict {(propiedad, corte): umbral_float}                  │
│                                                               │
│  PASO 2: Emparejar archivos ISA ↔ RAMS                        │
│    emparejar_subidos(isa_files, rams_files)                   │
│    _nombre_base_crudo("ISA_Maya.xlsx") → "Maya"               │
│    _nombre_base_crudo("RAMS_Maya.xlsx") → "Maya"              │
│    → Lista de pares (isa, rams) por nombre común              │
│                                                               │
│  PASO 3: Para cada par de crudos                              │
│    calcular_errores_crudo_df(df_isa, df_rams, ...)            │
│    │                                                          │
│    ├─ detectar_cortes_en_df(df_isa)                           │
│    │   → [(col_original, col_canonizada), ...]                │
│    │                                                          │
│    ├─ Para cada propiedad en ISA:                             │
│    │   ├─ canon_prop("Densidad a 15°C") → "DENSIDAD"          │
│    │   ├─ Calcular error |ISA - RAMS| por corte               │
│    │   └─ clasificar_propiedad(errores, prop, umbrales, ...)  │
│    │       ├─ Para cada corte: buscar umbral                  │
│    │       ├─ Si error > 3×umbral → ROJO absoluto             │
│    │       ├─ Si Azufre/Densidad → regla especial (3×)        │
│    │       ├─ Si corte pesado → tolerancia ampliada           │
│    │       └─ Agregar: si % verdes ≥ umbral → VERDE global    │
│    │                                                          │
│    └─ Acumular en resumen {prop → {crudo → semaforo}}         │
│                                                               │
│  PASO 4: Construir semáforo global por crudo                  │
│    _sem_global_por_crudo(resumen, pct_ok_amarillo, ...)       │
│                                                               │
│  PASO 5: Generar Excel en memoria                             │
│    exportar_resultados_a_bytes(hojas, resumen, ...)           │
│    → bytes del .xlsx (sin escritura a disco)                  │
└───────────────────┬───────────────────────────────────────────┘
                    │ devuelve (df_resumen, hojas, excel_bytes)
                    ▼
┌───────────────────────────────────────────────────────────────┐
│  app.py — Área principal de resultados                        │
│                                                               │
│  📊 Tabla resumen (Propiedad × Crudo) con emojis              │
│  📑 Expander por crudo:                                       │
│     Tab "Semáforo" → tabla con colores por propiedad          │
│     Tab "Errores"  → valores numéricos crudos                 │
│  💾 Botón descarga Excel                                      │
└───────────────────────────────────────────────────────────────┘
                    │
                    ▼
            USUARIO descarga
            Validacion_RAMS_ISA.xlsx
```

---

## 6. Objetivo y funcionamiento de cada archivo

### `app.py` — Entrypoint y orquestador UI

**Objetivo:** Es el punto de entrada que Streamlit ejecuta. Dibuja la interfaz, recoge los inputs del usuario, llama al core, y muestra los resultados.

**Responsabilidades:**
- Configurar la página (`st.set_page_config`)
- Inicializar `st.session_state` para persistir archivos y resultados entre reruns (evita que se pierdan los archivos al mover un slider)
- Renderizar el sidebar: uploaders de archivos, parámetros numéricos, botón de ejecución
- Validar parámetros antes de ejecutar (`pct_ok_amarillo > pct_rojo_rojo`)
- Llamar a `run_validation_in_memory()` del core
- Mostrar feedback de emparejamiento (qué archivos no tienen par)
- Renderizar resultados en dos niveles: resumen global y detalle por crudo con tabs
- Ofrecer descarga del Excel via `st.download_button`

**NO hace:** cálculos de errores, clasificaciones, construcción de umbrales.

---

### `core/validator_core.py` — Motor de validación

**Objetivo:** Contiene el 100% de la lógica de negocio, completamente aislada de Streamlit. Puede importarse y testearse sin ningún contexto web.

**Módulos internos:**

#### Normalización de texto

| Función | Qué hace |
|---------|----------|
| `strip_accents(text)` | Elimina acentos Unicode (NFD + filtro Mn). `"Densidád"` → `"Densidad"` |
| `canon_prop(s, alias)` | Canoniza nombre de propiedad: mayúsculas, sin puntos/grados, sin acentos, aplica alias. `"Densidad a 15°C"` → `"DENSIDAD"` |
| `canon_corte(s)` | Canoniza nombre de corte: normaliza guiones tipográficos (—, –, ‒...), espacios unicode, grados. `"150 – 200"` → `"150-200"` |

#### Lectura de umbrales

| Función | Qué hace |
|---------|----------|
| `detectar_columna_tipo(df)` | Localiza la columna "Tipo" de la matriz de umbrales buscando por nombre (`tipo`, `columna1`, `categoria`) o por contenido (busca celdas con "REPRO", "ADMISIBLE", "REPET") |
| `normalizar_tipo(raw)` | Limpia el texto de una celda de tipo (quita asteriscos, espacios no estándar) |
| `construir_umbrales(df, alias)` | Recorre la matriz de umbrales fila a fila, acumulando `{(prop_canon, corte_canon): umbral}`. Si hay varios valores para la misma clave, conserva el mayor |

#### Reglas de clasificación

| Función | Qué hace |
|---------|----------|
| `es_corte_pesado(corte)` | Devuelve `True` si el corte es C6–C10 o si su temperatura de inicio es ≥ 299 °C |
| `_buscar_umbral(umbrales, prop, corte)` | Busca el umbral con fallback: primero busca `(prop, corte)`, luego `(prop_base, corte)` (ej. "PESO ACUMULADO" → "PESO") |
| `clasificar_propiedad(...)` | Función central. Clasifica todos los cortes de una propiedad y devuelve el semáforo global + corte peor + error peor |

#### Lectura de archivos

| Función | Qué hace |
|---------|----------|
| `leer_tabla_errores_filelike(bytes, filename, sheet)` | Lee cualquier archivo soportado a DataFrame operando 100% en memoria (BytesIO). Detecta extensión y llama al engine correcto |
| `_leer_excel(bio, filename, sheet, ext)` | Usa el engine estricto por extensión para evitar errores cruzados (xlrd no abre .xlsx en v2+) |
| `_leer_csv(bio, filename)` | Prueba separadores `;`, `,`, `\t`, `\|` en orden. Si ninguno da más de 1 columna, usa auto-detección de pandas |

#### Motor de cálculo

| Función | Qué hace |
|---------|----------|
| `detectar_cortes_en_df(df)` | Detecta columnas de cortes en un DataFrame, excluyendo metadatos conocidos (Propiedad, Unidad, Validacion...) |
| `crear_semantica_alias()` | Construye el diccionario de aliases: mapea variantes de nombres de propiedades a su forma canónica (ej. "Viscosidad 50C", "Viscosidad a 50C" → "VISCOSIDAD 50") |
| `_nombre_base_crudo(fname)` | Extrae el nombre del crudo del nombre del archivo. Detecta códigos estructurados (ABC-2024-001) o elimina prefijos/sufijos ISA/RAMS |
| `calcular_errores_crudo_df(...)` | Para un par ISA/RAMS: calcula errores por propiedad×corte, llama a clasificar_propiedad, acumula en el resumen global |
| `_sem_global_por_crudo(resumen, ...)` | Agrega los semáforos de todas las propiedades de un crudo en un semáforo único global |
| `emparejar_subidos(isa_files, rams_files)` | Empareja listas de (nombre, bytes) por nombre base del crudo. Loguea los sin par |

#### Exportación

| Función | Qué hace |
|---------|----------|
| `add_conditional_formatting_text(ws, rango)` | Añade reglas de formato condicional Excel (verde/amarillo/rojo/gris) por texto |
| `escribir_hoja_df(ws, df)` | Escribe un DataFrame en una hoja openpyxl con cabecera en negrita y autoajuste de columnas |
| `exportar_resultados_a_bytes(...)` | Construye el workbook completo en memoria: hoja Resumen + una hoja por crudo. Devuelve bytes sin tocar disco |
| `run_validation_in_memory(...)` | **Pipeline orquestador**: lee umbrales → empareja → calcula → exporta. Devuelve todo lo que necesita la UI |

---

### `ui/styling.py` — Presentación visual

**Objetivo:** Funciones puras de presentación para Streamlit. No calcula nada — solo aplica colores y emojis a datos ya calculados por el core.

| Función | Qué hace |
|---------|----------|
| `map_emoji(v)` | Convierte `"VERDE"` → `"🟢"`, `"AMARILLO"` → `"🟡"`, `"ROJO"` → `"🔴"` |
| `style_semaforo_column(df, col)` | Aplica `PatternFill` CSS a una columna de semáforo. Compatible con pandas ≥ 2.0 y < 2.1 (usa `map()` o `applymap()` según versión) |
| `style_matrix(df)` | Aplica colores de semáforo a toda la matriz de resumen (todas las columnas salvo "Propiedad") |

**Paleta de colores:**
```python
PALETA = {
    "VERDE":    "#C6EFCE",   # verde suave Excel
    "AMARILLO": "#FFEB9C",   # amarillo suave Excel
    "ROJO":     "#FFC7CE",   # rojo suave Excel
    "NA":       "#E7E6E6",   # gris para sin umbral
    "":         "#FFFFFF",   # blanco para vacíos
}
```

---

### `.streamlit/config.toml` — Configuración visual

Define el tema visual de la aplicación:

```toml
[theme]
primaryColor      = "#0A66C2"    # azul corporativo (botones, sliders)
backgroundColor   = "#FFFFFF"    # fondo principal
secondaryBackgroundColor = "#F5F7FB"  # sidebar y expanders
textColor         = "#222222"
font              = "sans serif"
```

---

### `requirements.txt` — Dependencias de despliegue

Lista las dependencias de Python que Streamlit Cloud instala al desplegar la app. Los rangos de versión son deliberados:
- Sin pinear versión exacta de Streamlit (Cloud puede tener una más nueva)
- Con límite superior para evitar roturas por major versions
- Con comentario explicativo sobre las limitaciones de `xlrd`

---

### `tests/test_validator_core.py` — Suite de tests

42 tests unitarios organizados en 12 clases que cubren:

| Clase | Qué prueba |
|-------|------------|
| `TestStripAccents` | Eliminación de acentos y manejo de None |
| `TestCanonProp` | Canonización con y sin alias, casos borde |
| `TestCanonCorte` | Normalización de guiones, espacios, grados |
| `TestEsCorteePesado` | Detección C6-C10, temperaturas ≥ 299°C |
| `TestConstruirUmbrales` | Construcción desde matriz, umbral mayor gana, errores |
| `TestClasificarPropiedad` | Verde/amarillo/rojo, rojo absoluto, NA, reglas especiales |
| `TestSemGlobalPorCrudo` | Agregación global por crudo |
| `TestNombreBaseCrudo` | Extracción de nombre desde distintos patrones de archivo |
| `TestEmparejarSubidos` | Emparejamiento ISA↔RAMS, casos sin par, parciales |
| `TestLeerTablaErroresFilelike` | Lectura xlsx, csv, formato no soportado, archivo corrupto |
| `TestFloatOrNone` | Conversión de valores con coma decimal, vacíos, texto |
| `TestDetectarCortes` | Exclusión de metadatos, DataFrames sin cortes |

---

## 7. Cómo funciona por dentro — lógica detallada

### 7.1 Emparejamiento de archivos

El sistema usa `_nombre_base_crudo()` para extraer el nombre del crudo de cada archivo:

```
ISA_Maya.xlsx            → "Maya"
RAMS_Maya.xlsx           → "Maya"   ✅ par encontrado

ISA_CrudoBrent.xlsx      → "CrudoBrent"
RAMS-CrudoBrent.xlsx     → "CrudoBrent"  ✅ par encontrado

ABC-2024-001_ISA.xlsx    → "ABC-2024-001"  (código estructurado)
ABC-2024-001_RAMS.xlsx   → "ABC-2024-001"  ✅ par encontrado

ISA_Extra.xlsx           → "Extra"
(sin RAMS correspondiente)  ⚠️ advertencia en UI
```

El algoritmo:
1. Quita la extensión
2. Busca patrón de código estructurado (`ABC-2024-001`)
3. Si no, elimina prefijo `ISA_` / `RAMS_` al inicio
4. Elimina sufijo `_ISA` / `_RAMS` (con versión opcional: `_ISA_v2`)

### 7.2 Construcción de la matriz de umbrales

La matriz de umbrales tiene este formato típico:

| Propiedad | Tipo | 150-200 | 200-250 | 300+ |
|-----------|------|---------|---------|------|
| DENSIDAD | Reproductibilidad | 0.5 | 0.8 | 1.2 |
| DENSIDAD | Admisible | 0.3 | 0.5 | 0.8 |
| AZUFRE | Reproductibilidad | 0.1 | 0.2 | 0.4 |

El sistema:
1. Detecta la columna "Propiedad" y la columna "Tipo"
2. **Solo acepta filas** donde el Tipo contiene "REPRO", "ADMISIBLE" o "REPET"
3. Para cada celda de corte, construye la clave `(prop_canon, corte_canon)`
4. Si hay varias filas para la misma clave, **conserva el umbral mayor**
5. Los nombres de propiedad se canonizabzan (acentos, mayúsculas, aliases)

### 7.3 Cálculo de errores

Para cada propiedad de ISA que también aparece en RAMS:

```
error(propiedad, corte) = |ISA_valor - RAMS_valor|
```

Si ISA o RAMS no tienen valor para ese corte → `None` (se muestra como N/D).

### 7.4 Clasificación por semáforo (reglas por capas)

La clasificación se aplica en este orden de prioridad:

```
Para cada corte:

┌─ ¿El error es None o no numérico?
│   └─ Estado: "(no numérico)" — no cuenta
│
├─ ¿Existe umbral para esta (propiedad, corte)?
│   └─ NO → Estado: "(sin umbral)" — no cuenta para el semáforo
│
├─ ¿Error > 3 × umbral?
│   └─ SÍ → Estado: ROJO (rojo absoluto) → activa bandera rojo_absoluto
│
├─ ¿Propiedad es AZUFRE o DENSIDAD? (regla especial de dominio)
│   ├─ Error ≤ 3 × umbral → VERDE
│   └─ 2×umbral < Error ≤ 3×umbral → AMARILLO
│
└─ Regla general:
    ├─ ¿Es corte pesado? (≥299°C o C6-C10)
    │   └─ umbral_amarillo = umbral × (1 + tolerancia_pesados)
    └─ No pesado:
        └─ umbral_amarillo = umbral × (1 + tolerancia_estándar)
    
    Error ≤ umbral          → VERDE
    umbral < Error ≤ umbral_amarillo → AMARILLO
    Error > umbral_amarillo → ROJO
```

**Semáforo global de la propiedad** (agrega todos los cortes):

```
Si se activó rojo_absoluto → ROJO (independiente del resto)

Si NO hay ningún corte con umbral → NA

En caso contrario:
  % rojos   > umbral_rojo_global  → ROJO
  % verdes  ≥ umbral_verde_global → VERDE
  otro caso                       → AMARILLO
```

### 7.5 Semáforo global por crudo

Se calcula sobre todos los semáforos de propiedad del crudo:

```
Si % propiedades rojas  > pct_rojo_rojo   → ROJO
Si % propiedades verdes ≥ pct_ok_amarillo → VERDE
Otro caso                                 → AMARILLO
```

### 7.6 Generación del Excel

El Excel de salida contiene:

- **Hoja "Resumen"**: matriz Propiedad × Crudo con semáforos. Primera fila = GLOBAL (semáforo del crudo completo). Formato condicional por color activado en Excel (funciona aunque el usuario cambie valores).
- **Una hoja por crudo**: columnas Propiedad, Semáforo, Corte_peor, Error_peor, Umbral_peor, y una columna por cada corte con el error numérico absoluto. Columna Semáforo con formato condicional.

Todo se genera en memoria con `io.BytesIO` — ningún byte se escribe en disco del servidor.

---

## 8. Formatos de archivo soportados

### Archivos ISA y RAMS

| Formato | Engine | Notas |
|---------|--------|-------|
| `.xlsx` | `openpyxl` | Formato moderno de Excel. El más recomendado |
| `.xls` | `xlrd` | Formato Excel 97-2003. xlrd ≥ 2.0 NO abre `.xlsx` |
| `.xlsb` | `pyxlsb` | Excel binario comprimido |
| `.csv` | `pandas` | Auto-detecta separador (`;`, `,`, `\t`, `\|`). Soporta coma decimal |

### Estructura requerida de los archivos ISA/RAMS

Los archivos ISA y RAMS deben tener:
- Una columna llamada **`Propiedad`** (exactamente ese nombre, puede tener acentos)
- Una columna por cada corte de destilación (los nombres se normalizan automáticamente)
- Opcionalmente: columnas `Unidad`, `Validacion` (se ignoran)

Ejemplo mínimo:

| Propiedad | 150-200 | 200-250 | 300+ |
|-----------|---------|---------|------|
| Densidad | 850.5 | 860.2 | 875.0 |
| Viscosidad 50 | 5.2 | 8.1 | 15.3 |
| Azufre | 0.15 | 0.28 | 0.45 |

### Estructura requerida de la matriz de umbrales

| Propiedad | Tipo | 150-200 | 200-250 | 300+ |
|-----------|------|---------|---------|------|
| DENSIDAD | Reproductibilidad | 0.5 | 0.8 | 1.2 |
| AZUFRE | Reproductibilidad | 0.10 | 0.20 | 0.40 |

- La columna de Tipo puede llamarse: `Tipo`, `Columna1`, `Categoria`, o ser detectada automáticamente por contenido
- Solo las filas con Tipo que contenga "REPRO", "ADMISIBLE" o "REPET" se usan como umbrales

### Convención de nombres de archivo para el emparejamiento

El sistema es tolerante a variaciones de nombre:

```
✅ Válido (se emparejan correctamente):
   ISA_Crudo_Maya.xlsx  ↔  RAMS_Crudo_Maya.xlsx
   Crudo_Maya_ISA.xlsx  ↔  Crudo_Maya_RAMS.xlsx
   ISA-CrudoMaya.xlsx   ↔  RAMS-CrudoMaya.xlsx
   CrudoMaya.xlsx       ↔  CrudoMaya_RAMS.xlsx

❌ No se emparejan (nombres base diferentes):
   ISA_Maya.xlsx        ↔  RAMS_Brent.xlsx
```

---

## 9. Cómo se usa — guía paso a paso

### Paso 1: Preparar la matriz de umbrales

Asegúrate de que tu archivo Excel de umbrales tiene:
- Columna `Propiedad` con los nombres de propiedades
- Columna de tipo (`Tipo` o similar) con los valores `Reproductibilidad` / `Admisible`
- Columnas de cortes con los valores numéricos de umbral

### Paso 2: Preparar los archivos ISA y RAMS

- Nombra los archivos con el mismo nombre base del crudo: `ISA_Maya.xlsx` y `RAMS_Maya.xlsx`
- Verifica que ambos tienen columna `Propiedad` y las mismas columnas de cortes
- Puedes subir múltiples crudos a la vez (varios ISA + varios RAMS)

### Paso 3: Abrir la aplicación

Accede a la URL de Streamlit Cloud donde está desplegada la app, o ejecuta localmente:
```bash
streamlit run app.py
```

### Paso 4: Subir los archivos en el sidebar

1. **Matriz de umbrales**: sube el archivo Excel de umbrales. Si tiene varias hojas, escribe el nombre de la hoja en el campo "Nombre de hoja" (vacío = primera hoja).
2. **Archivos ISA**: sube uno o más archivos ISA.
3. **Archivos RAMS**: sube los correspondientes archivos RAMS.

Verás confirmación verde del número de archivos cargados.

### Paso 5: Configurar los parámetros

| Parámetro | Descripción | Valor por defecto |
|-----------|-------------|-------------------|
| Tolerancia estándar | Margen adicional sobre el umbral para clasificar como AMARILLO en cortes normales | 0.10 (10%) |
| Tolerancia cortes pesados | Margen ampliado para cortes ≥ 299°C o C6-C10 (más difíciles de modelar) | 0.60 (60%) |
| Umbral VERDE global (%) | Si el X% o más de propiedades son verdes, el crudo es VERDE globalmente | 0.90 (90%) |
| Umbral ROJO global (%) | Si más del X% de propiedades son rojas, el crudo es ROJO globalmente | 0.30 (30%) |

### Paso 6: Validar

Pulsa **"✅ Validar ahora"**. El botón está desactivado hasta que hayas subido todos los archivos necesarios.

Si algún archivo ISA no tiene par RAMS (o viceversa), verás una advertencia antes de los resultados, pero la validación continúa con los pares encontrados.

### Paso 7: Interpretar los resultados

**Tabla resumen (Propiedad × Crudo):**
- Filas = propiedades analizadas
- Columnas = crudos procesados
- Primera fila = GLOBAL (semáforo del crudo completo)
- Cada celda muestra el semáforo de esa propiedad para ese crudo

**Detalle por crudo (expanders):**
- Tab **Semáforo**: propiedad, semáforo global, corte más problemático, error en ese corte, umbral aplicado
- Tab **Errores**: valores numéricos absolutos de `|ISA - RAMS|` por corte

### Paso 8: Descargar el informe

Pulsa **"💾 Descargar Excel con formato"** para obtener el archivo `.xlsx` con todo el análisis, incluyendo formato condicional de color (funciona al abrirlo en Excel/LibreOffice).

---

## 10. Instalación y ejecución local

### Requisitos previos

- Python 3.9 o superior
- Git

### Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/TU_USUARIO/validador-crudos-streamlit.git
cd validador-crudos-streamlit

# 2. Crear entorno virtual (recomendado)
python -m venv .venv

# Linux/Mac:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar secrets locales (ver sección 12)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# 5. Ejecutar la app
streamlit run app.py
```

La app se abre automáticamente en `http://localhost:8501`.

### Ejecutar los tests

```bash
pytest tests/ -v
```

Salida esperada:
```
tests/test_validator_core.py::TestStripAccents::test_strip[...] PASSED
tests/test_validator_core.py::TestCanonProp::test_canon_sin_alias[...] PASSED
...
42 passed in Xs
```

---

## 11. Despliegue en Streamlit Cloud

### Primera vez

1. Haz push del repositorio a GitHub (puede ser público o privado).
2. Ve a [share.streamlit.io](https://share.streamlit.io) e inicia sesión con tu cuenta de GitHub.
3. Clic en **"New app"**.
4. Selecciona el repositorio, la rama (`main`) y el archivo de entrada (`app.py`).
5. Añade los secrets (ver sección 12).
6. Clic en **"Deploy"**.

La app queda disponible en una URL pública del tipo `https://tu-app.streamlit.app`.

### Requerimientos del repositorio para Cloud

Streamlit Cloud requiere que existan en la raíz del repo:
- `app.py` (o el archivo indicado como entrypoint)
- `requirements.txt`

Los módulos `core/` y `ui/` deben tener sus `__init__.py` para que Python los encuentre correctamente.

### Consideraciones de memoria

Streamlit Cloud Community tiene ~1 GB de RAM. Los archivos Excel de laboratorio son pequeños (KB a pocos MB) — no debería haber problema. Si los archivos fueran muy grandes, considerar la versión Teams/Pro.

---

## 12. Configuración de secrets

### ¿Para qué se usan los secrets en este proyecto?

Actualmente los secrets se usan para almacenar valores de configuración por defecto que no se quieren hardcodear en el código. No hay credenciales de base de datos ni tokens en este proyecto.

### Configuración local

El archivo `.streamlit/secrets.toml` está en `.gitignore` — nunca se sube al repositorio.

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

El archivo de ejemplo contiene:

```toml
# .streamlit/secrets.toml
# No hay valores sensibles en este proyecto.
# Este archivo se deja como plantilla para futuras configuraciones.
[defaults]
# (reservado para valores configurables futuros)
```

### Configuración en Streamlit Cloud

1. En el dashboard de tu app → **Settings** → **Secrets**
2. Pegar el contenido del `.toml`
3. Guardar → la app se reinicia automáticamente

---

## 13. Tests unitarios

### Ejecutar

```bash
# Todos los tests con verbose
pytest tests/ -v

# Con reporte de cobertura (requiere pytest-cov)
pytest tests/ -v --cov=core --cov-report=term-missing

# Un test específico
pytest tests/test_validator_core.py::TestClasificarPropiedad -v
```

### Casos cubiertos por los tests

Los tests están diseñados para cubrir la **lógica real del dominio**, no casos genéricos:

```
TestStripAccents        → acentos, None, texto normal
TestCanonProp           → aliases de dominio (Densidad a 15°C → DENSIDAD,
                          NOR CLARO → RON, Carbono Conradson → RESIDUO DE CARBON)
TestCanonCorte          → guiones tipográficos, espacios unicode, grados
TestEsCorteePesado      → C6-C10, temperaturas exactas en límite (298°C vs 299°C)
TestConstruirUmbrales   → umbral mayor gana, errores de formato
TestClasificarPropiedad → regla especial Azufre/Densidad (3×umbral = verde),
                          corte pesado usa tolerancia ampliada,
                          PESO ACUMULADO hace fallback a PESO,
                          rojo absoluto (>3×umbral), sin umbral → NA
TestSemGlobalPorCrudo   → todo verde, mayoría rojos, caso mixto amarillo
TestNombreBaseCrudo     → prefijos, sufijos, versiones, código estructurado
TestEmparejarSubidos    → par exacto, sin pares, par parcial
TestLeerTablaErroresFilelike → xlsx, csv con `;` y `,` decimal, formato no soportado
TestFloatOrNone         → coma decimal, vacío, texto no numérico
TestDetectarCortes      → exclusión de metadatos (Propiedad, Unidad, Validacion)
```

### Añadir nuevos tests

El archivo `conftest.py` en la raíz añade el directorio al `sys.path`, así que los imports funcionan directamente:

```python
# tests/test_mi_funcion.py
from core.validator_core import mi_funcion

def test_caso_nuevo():
    resultado = mi_funcion(...)
    assert resultado == esperado
```

---

## 14. Publicar cambios (VS Code → GitHub → Cloud)

### Flujo de trabajo habitual

```bash
# 1. Hacer cambios en VS Code

# 2. Verificar que los tests siguen pasando
pytest tests/ -v

# 3. Añadir cambios a git
git add .

# 4. Commit con mensaje descriptivo
git commit -m "feat: descripción del cambio"
# o
git commit -m "fix: corrección de X"
# o
git commit -m "docs: actualización del README"

# 5. Push a la rama principal
git push origin main
```

Streamlit Cloud detecta el push automáticamente y redespliega la app en 1-2 minutos.

### Buenas prácticas de mensajes de commit

```
feat: nueva funcionalidad
fix: corrección de bug
docs: cambios en documentación
test: añadir o modificar tests
refactor: refactorización sin cambio de comportamiento
style: cambios de formato/estilo
```

### Ramas de trabajo (opcional para equipos)

```bash
# Crear rama para una nueva funcionalidad
git checkout -b feature/nueva-propiedad

# Trabajar... hacer commits...

# Merge a main cuando esté listo
git checkout main
git merge feature/nueva-propiedad
git push origin main
```

---

## 15. Preguntas frecuentes y resolución de problemas

### ❓ "No se encontraron pares ISA/RAMS"

**Causa:** Los nombres base de los archivos no coinciden después de eliminar los prefijos/sufijos ISA/RAMS.

**Solución:** Verifica que los archivos siguen la convención:
```
ISA_NombreCrudo.xlsx  ↔  RAMS_NombreCrudo.xlsx
```
El nombre base (sin ISA/RAMS, sin extensión) debe ser idéntico.

---

### ❓ "La matriz de umbrales no tiene columna 'Propiedad'"

**Causa:** La primera columna de tu matriz no se llama exactamente `Propiedad`.

**Solución:** Renombra la columna en tu archivo Excel a `Propiedad` (con mayúscula, sin acentos).

---

### ❓ "No se localiza columna 'Tipo'"

**Causa:** El sistema no puede detectar la columna que indica si es Reproductibilidad o Admisible.

**Solución:** Asegúrate de que la columna se llama `Tipo`, `Columna1` o `Categoria`, o que contiene celdas con el texto "REPRODUCTIBILIDAD", "ADMISIBLE" o "REPETIBILIDAD".

---

### ❓ Los semáforos del Excel no muestran color

**Causa:** El formato condicional de openpyxl es dinámico — requiere que Excel evalúe las reglas al abrir.

**Solución:** Abre el archivo en Microsoft Excel o LibreOffice Calc. Si usas Google Sheets, importa el archivo (Archivo → Importar). El formato condicional se activará al abrir.

---

### ❓ Error al leer un archivo `.xlsx` con engine `xlrd`

**Causa:** `xlrd ≥ 2.0` solo soporta `.xls`. Si ves este error, hay un archivo `.xlsx` siendo procesado con el engine equivocado.

**Solución:** El código ya maneja esto automáticamente usando el engine correcto por extensión. Si ves este error, es que el archivo tiene extensión `.xlsx` pero estructura interna de `.xls`. Guárdalo como `.xlsx` correctamente desde Excel.

---

### ❓ Los archivos subidos desaparecen al mover un slider

**Causa:** Streamlit re-ejecuta todo el script en cada interacción. Sin `session_state`, los uploaders se reinician.

**Solución:** La app usa `st.session_state` para persistir los archivos. Si experimentas este problema, asegúrate de estar usando la versión más reciente del código.

---

### ❓ Error de memoria en Streamlit Cloud

**Causa:** Streamlit Community tiene ~1 GB de RAM. Archivos muy grandes pueden saturarla.

**Solución:** Reduce el tamaño de los archivos o considera la versión Streamlit Teams/Pro. Para este caso de uso (archivos de laboratorio), no debería ser un problema.

---

### ❓ La app tarda mucho en procesar

**Causa:** Si hay muchos crudos o archivos muy grandes, el procesamiento puede tardar varios segundos.

**Solución:** El procesamiento es secuencial. Para acelerar con muchos crudos, se podría implementar `@st.cache_data` en la lectura de archivos. Esto es una mejora futura planificada.

---

## 16. Licencia

```
Copyright © 2024. Todos los derechos reservados.

Todo el código fuente, documentación y archivos contenidos en este repositorio
son propiedad exclusiva de su autor.

Queda PROHIBIDO:
- Copiar, distribuir o modificar este software sin autorización expresa por escrito
- Usar este software con fines comerciales o no comerciales sin licencia
- Usar el código para entrenar modelos de inteligencia artificial

La mera visualización del código en un repositorio público NO otorga ningún
derecho de uso, reproducción ni derivación.
```

> ⚠️ **Nota sobre repositorio público:** aunque el código es visible en GitHub, la licencia "All Rights Reserved" prohíbe su reutilización. Si el código contiene lógica propietaria sensible (fórmulas de validación, criterios de negocio), considera hacer el repositorio **privado**. Streamlit Cloud soporta repos privados con cuenta Team/Pro.

---

*Documentación generada para la versión mejorada del proyecto. Última actualización: feb 2026.*


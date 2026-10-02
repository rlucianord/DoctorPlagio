# Corpus de Copy/Paste de DoctorPlagio

## Objetivo

DoctorPlagio separa tres problemas:

1. **Copy/Paste:** coincidencia textual fuerte contra un corpus documental.
2. **Similitud semántica:** motor existente con MPNet + Chroma.
3. **Características compatibles con IA:** GPT-OSS + métricas lingüísticas.

El motor nuevo `app/backend/copypaste_engine.py` se ocupa solamente del punto 1.

## Cómo funciona

El motor utiliza:

- normalización de tokens;
- n-gramas de 8 palabras;
- fingerprints;
- selección tipo **Winnowing**;
- índice SQLite local;
- agrupación de coincidencias consecutivas;
- cálculo de cobertura del documento sin doble conteo;
- conservación de fuente, archivo, posición y, cuando existe, página.

No convierte similitud semántica en porcentaje de plagio.

## Estructura

```text
DoctorPlagio/
├── app/backend/copypaste_engine.py
├── scripts/corpus_manager.py
├── data/
│   ├── corpus/
│   │   ├── CSIC/
│   │   ├── USC/
│   │   └── DoctorPlagio/
│   └── copypaste/
│       └── copypaste_index.sqlite3
└── docs/
    └── COPYPASTE_CORPUS_README.md
```

El índice SQLite se crea automáticamente y **no debe subirse a GitHub** si contiene documentos o datos derivados que no estén autorizados para redistribución.

## Paso 1 — Preparar carpetas

Desde `C:\PROYECTO\DoctorPlagio`:

```powershell
mkdir data\corpus
mkdir data\corpus\CSIC
mkdir data\corpus\USC
mkdir data\corpus\DoctorPlagio
mkdir data\copypaste
```

## Paso 2 — Crear el índice

```powershell
python scripts\corpus_manager.py init
```

## Paso 3 — CSIC Spanish Corpus

El CSIC Spanish Corpus contiene 30,929 documentos y 146,795,650 tokens de publicaciones científicas en español. El archivo principal `csic_es.txt` ocupa aproximadamente 929 MB. El registro de Zenodo indica CC BY 4.0 para el empaquetado del dataset y advierte de los derechos sobre el contenido original.

Fuente:
https://zenodo.org/records/7313126

Descarga manual:

1. Abrir la página.
2. Descargar `csic_es.txt`.
3. Guardarlo como:

```text
C:\PROYECTO\DoctorPlagio\data\corpus\CSIC\csic_es.txt
```

4. Ejecutar:

```powershell
python scripts\corpus_manager.py ingest-csic data\corpus\CSIC\csic_es.txt
```

El proceso puede tardar bastante. Es normal.

## Paso 4 — Corpus científico y académico de USC / Proxecto Nós

El corpus reúne textos en gallego y castellano de fuentes institucionales y académicas. La tarjeta actual indica 8,584 textos en castellano del Catálogo Minerva, además de publicaciones de USC y artículos científicos de Wikipedia; el corpus completo publicado en la tarjeta suma 83,437 documentos. La tarjeta indica licencia CC BY 4.0 para el dataset.

Fuente:
https://huggingface.co/datasets/proxectonos/corpus_dominio_cientifico

La estructura publicada es JSONL y contiene documentos en `es/`.

Descarga manual:

1. Abrir la página del dataset.
2. Descargar los archivos JSONL de la carpeta `es/`.
3. Mantener la estructura dentro de:

```text
C:\PROYECTO\DoctorPlagio\data\corpus\USC\
```

4. Para cada JSONL ejecutar:

```powershell
python scripts\corpus_manager.py ingest-jsonl "RUTA_DEL_ARCHIVO.jsonl" --source usc_cientifico --language es
```

El gestor lee un documento por línea y utiliza el campo `text`.

## Paso 5 — Documentos propios autorizados

Cualquier documento que tengamos derecho a utilizar como corpus puede incorporarse:

```powershell
python scripts\corpus_manager.py ingest-dir data\corpus\DoctorPlagio --source doctorplagio
```

Se admiten:

- PDF
- TXT
- MD
- DOCX

Para PDF se conserva la página mediante marcadores internos.

## Paso 6 — Consultar estadísticas

```powershell
python scripts\corpus_manager.py stats
```

Ejemplo:

```json
{
  "documentos": 10000,
  "fingerprints": 2500000,
  "fuentes": [
    {
      "fuente": "csic_es",
      "documentos": 9790
    }
  ]
}
```

## Paso 7 — PAN-PC-11: usarlo para validar, no como corpus comercial

PAN-PC-11 fue creado para evaluar algoritmos de detección de plagio. Su página indica 26,939 documentos y disponibilidad gratuita para investigación. No debemos incorporarlo automáticamente como corpus de producción de un producto comercial.

Fuente:
https://zenodo.org/records/3250095

La función de este dataset será crear pruebas conocidas:

```text
fuente original
       ↓
documento con plagio conocido
       ↓
DoctorPlagio
       ↓
¿encontró el bloque correcto?
```

## Paso 8 — Corpus español-inglés de PAN

El conjunto de experimentos de plagio cruzado incluye 20,000 archivos en total y, dentro de PAN, 2,921 pares alineados español-inglés con plagio simulado. Es útil para una futura fase de plagio traducido, pero no se incorpora al corpus comercial por defecto.

Fuente:
https://zenodo.org/records/5159398

## Paso 9 — CEREAL

CEREAL cubre documentos en español procedentes de OSCAR y clasificados por país, incluyendo 24 países hispanohablantes. Es interesante para investigación sobre variedades del español, pero su propia ficha advierte que los autores no poseen el copyright del texto procedente de Common Crawl.

Por esa razón **NO se incorpora automáticamente al corpus comercial de DoctorPlagio**.

Fuente:
https://zenodo.org/records/11387864

## Paso 10 — TDX

TDX contiene 9,790 tesis y 248,676,517 tokens, pero procede de tesis publicadas por universidades catalanas. Por la razón que ya identificamos, no será la fuente principal de DoctorPlagio.

Fuente:
https://zenodo.org/records/7313149

Puede estudiarse como fuente secundaria o de pruebas.

## Política de incorporación

Cada fuente debe tener:

- nombre;
- procedencia;
- idioma;
- licencia;
- URL;
- fecha de incorporación;
- hash del contenido;
- número de documentos;
- número de fingerprints.

**No se debe incorporar contenido al corpus comercial únicamente porque sea descargable.**

La licencia del dataset, la licencia del contenido original y las condiciones de redistribución deben comprobarse por separado.

## Arquitectura final

```text
                         DOCTORPLAGIO
                              |
                 +------------+------------+
                 |                         |
          CORPUS COPY/PASTE            CHROMA/MPNet
                 |                         |
          Winnowing/Fingerprints       similitud semántica
                 |                         |
                 +------------+------------+
                              |
                       Evidencia textual
                              |
                              v
                         Informe PDF
                              |
                       GPT-OSS separado
                     características de IA
```

## Principio importante

El crecimiento del corpus no debe cambiar el algoritmo.

Podemos pasar de:

```text
1,356 documentos
```

a:

```text
10,000
50,000
100,000+
```

manteniendo el mismo índice y añadiendo nuevas fuentes.

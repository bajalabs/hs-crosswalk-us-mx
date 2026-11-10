[English](README.md)

# hs-crosswalk-us-mx

[![CI](https://github.com/bajalabs/hs-crosswalk-us-mx/actions/workflows/ci.yml/badge.svg)](https://github.com/bajalabs/hs-crosswalk-us-mx/actions/workflows/ci.yml)
[![Código: MIT](https://img.shields.io/badge/c%C3%B3digo-MIT-blue.svg)](LICENSE)
[![Datos: CC0-1.0](https://img.shields.io/badge/datos-CC0--1.0-green.svg)](LICENSE-DATA)
[![Última versión](https://img.shields.io/github/v/release/bajalabs/hs-crosswalk-us-mx)](https://github.com/bajalabs/hs-crosswalk-us-mx/releases/latest)

La Tarifa Arancelaria Armonizada de los Estados Unidos (HTSUS) vigente en archivos abiertos y limpios, vinculada con
la tarifa de México (fracciones y NICO de la TIGIE) en el nivel compartido de 6 dígitos del Sistema Armonizado, para
quienes comercian a través de la frontera México–Estados Unidos.

> **Una coincidencia a 6 dígitos significa la misma subpartida internacional, no fracciones nacionales ni aranceles
> equivalentes.** Cada fracción estadounidense de una subpartida se empareja con cada línea mexicana de esa misma
> subpartida. Cuál par corresponde a un producto es una decisión de clasificación conforme a las reglas de cada país.
> Los capítulos 98 y 99 de la HTSUS y el capítulo 98 de la TIGIE son disposiciones nacionales fuera del Sistema
> Armonizado; se listan, pero nunca se emparejan.

## Inicio rápido

Descarga los archivos de la [última versión](https://github.com/bajalabs/hs-crosswalk-us-mx/releases/latest) y
verifícalos con `shasum -a 256 -c SHA256SUMS`. O genéralos desde un clon con Python 3.12 o posterior y nada más:

```sh
git clone https://github.com/bajalabs/hs-crosswalk-us-mx.git
cd hs-crosswalk-us-mx
python3 -m unittest                  # sin red, con los datos de prueba del repositorio
python3 -m hs_crosswalk fetch-us     # HTSUS 2026, revisión 22, de usitc.gov, con sha256 verificado
python3 -m hs_crosswalk fetch-mx     # zip CSV de tigie-nico-mx v1.0.0 en GitHub, con sha256 verificado
python3 -m hs_crosswalk build        # escribe dist/ y dist/SHA256SUMS
```

Si ya tienes los CSV de tigie-nico-mx, omite `fetch-mx` e indica su carpeta con `--mx-dir ruta/a/csv` o
`TIGIE_CSV_DIR=ruta/a/csv`. Con [uv](https://docs.astral.sh/uv/), antepón `uv run` (por ejemplo
`uv run python -m hs_crosswalk build`). La generación tarda unos segundos.

## Contenido

Generado a partir de la HTSUS 2026, revisión 22 (publicada el 2026-10-30), y de tigie-nico-mx v1.0.0:

| Archivo | Filas | Tamaño | Contenido |
|---|---:|---:|---|
| `us_hts.csv` | 29,861 | 12.0 MB | cada renglón con código de la HTSUS: 961 partidas, 2,093 subpartidas, 6,858 fracciones de 8 y 19,949 de 10 dígitos |
| `hs6.csv` | 5,612 | 1.7 MB | cada subpartida de 6 dígitos con su título en inglés (HTSUS) y en español (TIGIE) |
| `crosswalk.csv` | 76,134 | 4.7 MB | pares de línea estadounidense y línea mexicana por subpartida, más las líneas nacionales de ambos lados |
| `coverage.json`, `coverage_by_chapter.csv` | 98 capítulos | 19 KB | conteos, cobertura y forma de cada coincidencia |
| `hs-crosswalk-us-mx.sqlite` | todo lo anterior | 32 MB | las tablas anteriores, el árbol completo de la HTSUS, las tres tablas mexicanas y una vista lista para consultar |
| `build-manifest.json`, `SHA256SUMS` | | | fuentes con sha256, opciones y el hash de cada archivo |

### Cobertura

| | Cantidad |
|---|---:|
| subpartidas de 6 dígitos en total | 5,612 |
| presentes en Estados Unidos y en México | 5,612 |
| solo en Estados Unidos | 0 |
| solo en México | 0 |
| una línea de EE. UU. con una línea mexicana (1:1) | 1,829 |
| una línea de EE. UU. con varias mexicanas (1:n) | 499 |
| varias de EE. UU. con una mexicana (n:1) | 1,620 |
| varias con varias (n:n) | 1,664 |

Lado estadounidense: 35,805 renglones de origen, de los cuales 5,944 son agrupadores sin código. 23,529 líneas no
tienen subdivisión con código: 19,926 líneas de mercancías en los capítulos 01–97 (19,831 de 10 dígitos y 95 de 8
dígitos, relojes del capítulo 91 sin sufijo estadístico) y 3,603 líneas nacionales de los capítulos 98 y 99.

Lado mexicano: 5,619 subpartidas (5,612 del Sistema Armonizado y 7 del capítulo nacional 98), 8,183 fracciones y
11,528 NICO, de los cuales 11,507 están vigentes y 21 fueron suprimidos. La vinculación usa 11,556 líneas mexicanas:
los 11,507 NICO vigentes y 49 fracciones sin NICO (43 de ellas dicen `Prohibida`); 55 de estas líneas son del
capítulo 98.

Tabla de correspondencia: 72,476 pares coincidentes y 3,658 renglones nacionales (3,603 de EE. UU. y 55 de México).

## Esquema

Todos los CSV están en UTF-8, con encabezado y fin de línea LF. Los códigos son texto: conserva sus ceros a la
izquierda.

**`us_hts.csv`**, un renglón por cada renglón con código de la HTSUS, en el orden de la tarifa:

| Columna | Significado |
|---|---|
| `code` | el número HTS, solo dígitos (4, 6, 8 o 10) |
| `htsno` | el número HTS como se publica, `0101.21.00.10` |
| `level` | 4, 6, 8 o 10 |
| `indent` | la sangría publicada |
| `description` | el texto propio del renglón |
| `full_path` | las descripciones de todos los ascendientes y del renglón, agrupadores incluidos, unidas por ` > ` |
| `units` | unidades de cantidad, unidas por `; ` |
| `general`, `special`, `column2` | tasas arancelarias como se publican (columna 1 general, columna 1 especial, columna 2) |
| `quota_quantity`, `additional_duties` | como se publican; casi siempre vacías |
| `footnotes` | `(marca) [columnas] texto`, unidas por ` \| ` |
| `hs6` | la subpartida de 6 dígitos; vacía en los capítulos 98 y 99 |
| `chapter` | dos dígitos |
| `is_leaf` | 1 si el renglón no tiene subdivisión con código: las líneas que se declaran |
| `rate_line` | el `htsno` de la línea que lleva las tasas de este renglón (las líneas estadísticas heredan las de su fracción de 8 dígitos) |
| `source_row` | la posición del renglón en la exportación de la USITC |

**`hs6.csv`**: `hs6`, `title_en`, `title_es`, `in_us`, `in_mx` (1 o 0), `us_lines`, `mx_lines` (líneas usadas en la
tabla de correspondencia), `title_en_kind`, `title_en_path`. `title_en_kind` indica qué renglón de la HTSUS dio el
título: `subheading_row` (un renglón publicado de 6 dígitos, 2,092), `national_line` (la única línea nacional de la
subpartida, 3,510), `grouping_row` (un agrupador sin código que cubre exactamente la subpartida, 5), `heading_row`
(una partida con una sola subpartida, 4) o `first_line` (ningún renglón cubre la subpartida completa, 1: la 8424.89,
cuya primera línea es más estrecha que la subpartida).

**`crosswalk.csv`**: `us_hts10`, `mx_codigo10`, `hs6`, `match_level`, `notes`.

| `match_level` | Significado |
|---|---|
| `hs6` | ambas líneas están en la misma subpartida de 6 dígitos |
| `us_only` | la subpartida no tiene línea mexicana (ninguna en esta versión) |
| `mx_only` | la subpartida no tiene línea estadounidense (ninguna en esta versión) |
| `national` | una línea de los capítulos 98/99 de EE. UU. o del capítulo 98 de México; `hs6` vacío y sin pareja |

`us_hts10` lleva diez dígitos, salvo las 95 líneas del capítulo 91 que solo tienen ocho. `mx_codigo10` lleva el código
NICO (fracción + NICO, diez dígitos) o la fracción de ocho dígitos cuando no tiene NICO. `notes` da la forma de la
subpartida, por ejemplo `n:1 at HS-6 (US 3, MX 1)`, y señala líneas sin sufijo estadístico, fracciones sin NICO y
fracciones cuyo arancel dice `Prohibida`.

**SQLite**: tablas `us_hts`, `us_tree` (los 35,805 renglones de origen con su padre, agrupadores incluidos),
`us_footnotes`, `hs6`, `crosswalk`, `mx_subpartidas`, `mx_fracciones`, `mx_nicos` (con `current`),
`coverage_by_chapter` y `meta`; la vista `v_crosswalk` une cada par con ambas descripciones, la tasa general de EE. UU.
y el IGI mexicano.

## Ejemplos de consulta

De Estados Unidos a México, aguacates:

```sh
sqlite3 -header -column dist/hs-crosswalk-us-mx.sqlite \
  "SELECT us_htsno, us_description, us_general_rate, mx_codigo10, mx_descripcion, mx_igi
   FROM v_crosswalk WHERE us_hts10 LIKE '080440%'"
```

```text
us_htsno       us_description     us_general_rate  mx_codigo10  mx_descripcion       mx_igi
-------------  -----------------  ---------------  -----------  -------------------  ------
0804.40.00.20  Certified organic  11.2¢/kg         0804400100   Aguacates (paltas).  20
0804.40.00.40  Other              11.2¢/kg         0804400100   Aguacates (paltas).  20
0804.40.00.90  Other              11.2¢/kg         0804400100   Aguacates (paltas).  20
```

De México a Estados Unidos, tabletas electrónicas (NICO 8471.30.01.01), solo con Python:

```python
import csv
with open("dist/crosswalk.csv", encoding="utf-8") as fh:
    pares = [r for r in csv.DictReader(fh) if r["mx_codigo10"] == "8471300101"]
print(pares)
# [{'us_hts10': '8471300100', 'mx_codigo10': '8471300101', 'hs6': '847130',
#   'match_level': 'hs6', 'notes': '1:n at HS-6 (US 1, MX 2)'}]
```

Por qué una coincidencia no es una equivalencia: en la subpartida 2208.90, la línea estadounidense del aquavit
(2208.90.01.00) queda emparejada con los NICO mexicanos del tequila (2208.90.03.01, 2208.90.03.91), porque cada país
divide la misma subpartida a su manera. El par solo dice que ambas líneas están dentro de la 2208.90.

## Cómo se genera

| Fuente | Dónde | Derechos |
|---|---|---|
| HTSUS 2026, revisión 22, exportaciones JSON y CSV | [archivo de revisiones de la USITC](https://www.usitc.gov/harmonized_tariff_information/hts/archive/list) | obra del Gobierno de EE. UU., 17 U.S.C. §105 |
| Subpartidas, fracciones y NICO de la TIGIE | [tigie-nico-mx](https://github.com/bajalabs/tigie-nico-mx), versión v1.0.0, `tigie-nico-mx-csv.zip` | texto legal mexicano, LFDA art. 14 fr. VIII |

`manifests/sources.json` fija cada archivo con su URL y su sha256; `fetch-us` y `fetch-mx` rechazan un archivo cuyo
hash no coincide. Después, la generación:

1. Compara la exportación JSON de la HTSUS con la exportación CSV de la misma revisión, renglón por renglón (código,
   sangría, descripción, unidades, las tres tasas, cupo y aranceles adicionales) tras normalizar espacios. Revisión
   22: 35,805 renglones en cada una, 0 diferencias. La revisión 19 da 35,804 renglones y 19,831 líneas de mercancías
   de 10 dígitos, también sin diferencias. Si las exportaciones difieren, no se genera nada.
2. Reconstruye la jerarquía a partir de las sangrías: el padre de un renglón es el renglón anterior más cercano con
   menor sangría. Donde la sangría salta dos niveles (27 renglones, por ejemplo bajo 3821.00.00) no se inventa ningún
   ascendiente. Los agrupadores sin código se quedan en `full_path` y en `us_tree` y nunca salen como códigos.
3. Lee los archivos mexicanos del contrato. Un NICO con fecha de `baja` no está vigente (`build --as-of AAAA-MM-DD`
   conserva los NICO que terminan después de ese día). Los renglones mal formados se omiten y se listan en
   `build-manifest.json`; esta versión no tiene ninguno.
4. Empareja cada línea estadounidense con cada línea mexicana de la misma subpartida y lista aparte las líneas
   nacionales.
5. Escribe los archivos, la base SQLite y `SHA256SUMS`. Las mismas entradas dan salidas idénticas byte por byte.

Los títulos en inglés vienen de la HTSUS y los títulos en español de la TIGIE. No se usan datos de UN Comtrade ni
textos de la Organización Mundial de Aduanas.

## Limitaciones

- La coincidencia es solo a 6 dígitos. No se comparan las líneas nacionales por debajo de ese nivel, ni los aranceles,
  las unidades, las preferencias del T-MEC, las cuotas compensatorias ni las regulaciones no arancelarias.
- La HTSUS cambia cada pocas semanas; esta versión es la revisión 22. Los aranceles temporales del capítulo 99 y las
  notas que remiten a ellos son lo que más cambia. Consulta la [HTSUS vigente](https://hts.usitc.gov/) antes de usar
  una tasa.
- La exportación de la HTSUS no incluye las notas generales, de sección ni de capítulo, así que `us_hts.csv` no las
  tiene. Las unidades de las 95 líneas del capítulo 91 sin sufijo estadístico las fijan las notas estadísticas de ese
  capítulo, no el renglón.
- Las tasas mexicanas son las celdas de la TIGIE compiladas por tigie-nico-mx (`igi_vigente`, `ige_vigente`); su
  documentación explica sus fechas y decretos.
- Ambas tarifas siguen la edición 2022 del Sistema Armonizado. La edición 2027 entra en vigor el 1 de enero de 2027;
  habrá subpartidas que cambien y esta tabla se volverá a generar.
- Una subpartida (8424.89) no tiene un renglón de la HTSUS que la cubra exactamente; su título en inglés es la primera
  línea nacional y está marcado como `first_line`.
- Estos archivos no son asesoría legal ni una publicación oficial. Prevalecen la HTSUS publicada por la USITC y la
  TIGIE publicada en el Diario Oficial de la Federación.

## Licencia

Código: [MIT](LICENSE). Datos: [CC0 1.0](LICENSE-DATA) para la compilación; la HTSUS y la TIGIE no tienen derechos de
autor (17 U.S.C. §105; Ley Federal del Derecho de Autor, art. 14, fr. VIII).

## Cita

Consulta [CITATION.cff](CITATION.cff), o cita: Baja Labs (2026). *hs-crosswalk-us-mx* (versión 1.0.0).
https://github.com/bajalabs/hs-crosswalk-us-mx

## Contribuir

Los reportes de errores en los datos y las solicitudes de cambio son bienvenidos; consulta
[CONTRIBUTING.md](CONTRIBUTING.md). Reportes de seguridad: [SECURITY.md](SECURITY.md).

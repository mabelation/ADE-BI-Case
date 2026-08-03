# Examen técnico — Líder de BI y Analítica Avanzada

**Caso: ADE Group (Alambres de Europa)** · Modalidad: take-home, 72 horas · Defensa oral: 60 min

---

## 1. Contexto

ADE Group es un fabricante europeo de mallas, alambres y cercas con tres filiales
productoras, cada una con su propio ERP heredado de la época previa a la fusión del grupo:

| Filial | Planta | Sistema | Mercados que atiende |
|---|---|---|---|
| **Indabel NV** | Deinze (Bélgica) | SAP | BE, NL, DE, FR, GB, SE |
| **Eurolam Sp. z o.o.** | Zawiercie (Polonia) | StalexERP v7.3 | PL, CZ, SK, HU |
| **Turio Alambres S.L.** | Valencia (España) | GestionMax | ES, PT, IT |

El grupo acaba de crear la Dirección de Datos y tú serías su primer líder de BI y
Analítica Avanzada. Hoy, cada filial reporta sus ventas con reglas propias y la
Dirección Comercial **no confía en las cifras consolidadas**: los totales nunca cuadran
entre reportes, y nadie sabe decir cuánto vende realmente el grupo a cliente final.

Te entregamos los extractos crudos de los tres ERPs, el sistema central de pedidos (OMS)
y los catálogos maestros disponibles. **Los datos reflejan la realidad de los sistemas de
ADE: contienen las mismas imperfecciones que encontrarías en producción.** Descubrirlas y
tratarlas correctamente es parte central de la evaluación. No se ha alterado nada "para
hacerlo difícil" que no hayamos visto antes en sistemas reales.

## 2. Los datos

```
datos/
├── erp-indabel-belgica/    extractos SAP (parquet) + maestro de clientes
├── erp-eurolam-polonia/    extractos StalexERP (csv) + maestro de clientes
├── erp-turio-espana/       informes mensuales GestionMax (xlsx) + maestro de clientes
├── oms-pedidos/            pedidos del Order Management System del grupo (parquet)
└── maestros/               productos, costos estándar, tipos de cambio,
                            comerciales-territorios, CRM de clientes del grupo
```

Ver `diccionario-datos.md` para el detalle de columnas (la documentación es la que
existe; en algunos sistemas está incompleta, como en la vida real).

## 3. Retos

### Reto 1 — Ingesta y consolidación (obligatorio)

Construye un pipeline reproducible que unifique facturación y pedidos de las tres
filiales en un modelo consolidado y limpio, con al menos:

- Importes en **EUR** y volúmenes en **toneladas**, homologados entre fuentes.
- Distinción explícita entre **venta a cliente final** y flujos **intercompañía**.
- Notas de crédito/devoluciones con el **signo correcto**.
- Sin duplicados; claves de producto y cliente homologadas entre sistemas.
- Reglas de calidad documentadas: qué encontraste, qué decidiste y por qué.
  Cada supuesto debe quedar escrito.

### Reto 2 — Forecast de demanda (obligatorio)

Pronostica las **toneladas mensuales por familia de producto** (total grupo, cliente
final) para **julio–diciembre 2026**. Justifica la metodología, muestra backtesting
honesto sobre la historia y explica tus errores. Presta atención a los eventos
atípicos del pasado: decide y documenta cómo los tratas.

### Reto 3 — Riesgo de abandono de clientes B2B (obligatorio)

La Dirección Comercial quiere una lista priorizada de **clientes activos en riesgo de
abandono**. Define un target defendible, construye el modelo que consideres apropiado y
explica qué señales usa. Se evaluará el rigor metodológico de la definición y la
evaluación tanto como el modelo mismo.

### Reto 4 — Rentabilidad: decisiones para ganar +2.0 pp (obligatorio)

Pregunta textual del Director General: *"¿Qué decisiones debe tomar el negocio para
aumentar el margen bruto consolidado en 2.0 puntos porcentuales durante los próximos
12 meses (jul-2026 a jun-2027)?"* (con los datos disponibles, el margen bruto —venta
neta menos costo estándar— es el proxy de rentabilidad del grupo).

Analiza dónde ganamos y dónde perdemos dinero (cliente, familia, filial, territorio)
y tradúcelo en **palancas cuantificadas con los datos**: cada decisión debe decir
cuántos pp aporta y bajo qué supuestos. El efecto debe proyectarse **sobre los
volúmenes de tu forecast (Reto 2)**, no sobre el pasado. La respuesta se entrega como
presentación de 3 slides (ver entregable 4).

## 4. Entregables

1. **Repositorio de código** (zip o repo git):
   - Scripts `.py` / `.sql` / dbt / lo que elijas — **prohibido entregar notebooks**
     (`.ipynb` en la entrega = descalificación del reto 1). Queremos ver código de
     ingeniería: modular, con un punto de entrada único (`main.py`, `Makefile` o
     equivalente) que reconstruya todo de cero.
   - `README.md`: cómo ejecutar, decisiones de arquitectura, supuestos.
   - Las herramientas son libres (pandas, DuckDB, Polars, dbt, SQLite…) pero debes
     justificar la elección como si fuera una decisión de plataforma para el equipo.
2. **Tabla de cifras de control** (`cifras-control.csv`): por mes — toneladas,
   venta neta EUR a cliente final, margen bruto %, nº de facturas. Es la evidencia
   de que tu limpieza es correcta; se contrastará contra nuestra referencia.
3. **Resumen ejecutivo** (1 página, PDF o MD) para dirección **no técnica**, que
   incluya obligatoriamente estos KPIs:
   - Venta neta a cliente final 2025 (M€) y toneladas 2025 (kt)
   - Margen bruto 2025 (%)
   - Venta neta y toneladas 2026 S1
   - **Flujos intercompañía**: volumen (kt) y venta (M€) 2025 y 2026 S1,
     desglosados por filial de destino
   - Top-3 países por venta 2025
   - Clientes activos en 2026 S1
   - Los 3 hallazgos que la dirección debe conocer, en lenguaje de negocio
4. **Presentación de decisiones** (exactamente 3 slides, sobre
   `plantilla-presentacion.pptx` incluida en esta carpeta): tu respuesta al Reto 4.
   - **Slide 1 — Portada**: tu nombre, puesto al que aplicas y los campos de la
     plantilla.
   - **Slide 2 — Narrativa**: respeta el mecanismo de comunicación de la plantilla:
     título declarativo, mensaje a destacar debajo del título, cuerpo donde
     explicas/defiendes/justificas ese mensaje, y panel derecho con
     **3 key takeaways** y **3 key actions** (verbo en infinitivo +
     `[Responsable · fecha]`).
   - **Slide 3 — Conclusiones**: lienzo libre — ilustra y articula como quieras,
     respetando solo el formato (encabezado y pie) de la plantilla.

## 5. Reglas del juego

- **72 horas** desde la recepción de los datos.
- Puedes usar asistentes de IA (Copilot, Claude, ChatGPT…). Decláralo en el README.
  En la defensa oral deberás poder explicar y modificar cualquier línea de tu código.
- Todo debe correr de punta a punta en una máquina limpia con instrucciones del README.
- Si algo es ambiguo: **decide, documenta y sigue** — evaluamos criterio, no adivinación.

## 6. Criterios de evaluación (resumen)

| Dimensión | Peso |
|---|---|
| Calidad de la ingesta y limpieza (hallazgos y tratamiento) | 30% |
| Exactitud de las cifras de control | 15% |
| Ingeniería: estructura, reproducibilidad, tests | 15% |
| Forecast: metodología y honestidad del backtesting | 12% |
| Churn: rigor del target y del proceso de evaluación | 12% |
| Rentabilidad: palancas cuantificadas para +2.0 pp | 8% |
| Comunicación ejecutiva: resumen + presentación de decisiones | 8% |

Suerte. Nos interesa cómo piensas, no solo cuánto sabes.

# ADE Group — Caso Práctico de BI y Analítica

## 1. Resumen ejecutivo

Este proyecto integra información comercial proveniente de tres filiales europeas y tres ERPs distintos en un único modelo canónico de ventas.

La solución incluye:

- ingesta y estandarización de datos;
- controles de calidad y trazabilidad;
- homologación corporativa de clientes y productos;
- conversión de unidades y monedas;
- separación entre ventas a cliente final e intercompañía;
- forecast de demanda, precio medio y revenue;
- Customer Health y priorización comercial;
- análisis de palancas para mejorar el margen bruto.

El resultado es una base analítica reproducible que permite transformar datos heterogéneos en decisiones comerciales cuantificables.

## 2. Objetivo del caso

Construir una solución reproducible que permita:

1. Consolidar la información comercial de ADE Group.
2. Generar cifras de control confiables.
3. Pronosticar ventas y volumen para julio–diciembre de 2026.
4. Identificar clientes con señales de deterioro comercial.
5. Proponer decisiones para aumentar el margen bruto consolidado en +2.0 puntos porcentuales durante los próximos 12 meses.

## 3. Fuentes de datos

| Filial | País | ERP / formato principal |
|---|---|---|
| Indabel | Bélgica | SAP / Parquet |
| Eurolam | Polonia | StalexERP / CSV |
| Turio | España | GestiónMax / Excel |

Fuentes complementarias:

- CRM corporativo de clientes.
- Maestro corporativo de productos.
- Costos estándar.
- Tipos de cambio.
- OMS de pedidos.
- Maestro de comerciales y territorios.

## 4. Arquitectura de la solución

```text
Fuentes originales
       ↓
Ingesta por ERP
       ↓
Staging estandarizado
       ↓
Reglas de calidad y negocio
       ↓
Modelo canónico de ventas
       ↓
Reporting y analítica
       ├── Cifras de control
       ├── Forecast
       ├── Customer Health
       └── Margin Intelligence
```

El forecast, Customer Health y rentabilidad consumen la misma tabla canónica, evitando definiciones distintas de ventas entre módulos.

## 5. Estructura del repositorio

```text
ADE-BI-Case/
│
├── data/
│   ├── raw/
│   ├── staging/
│   └── curated/
│
├── outputs/
│
├── src/
│   ├── ingestion/
│   │   ├── eurolam.py
│   │   ├── indabel.py
│   │   └── turio.py
│   ├── transformations/
│   │   └── canonical_sales.py
│   ├── reporting/
│   │   └── control_figures.py
│   ├── forecasting/
│   │   ├── forecasting.py
│   │   ├── forecast_v2.py
│   │   └── forecast_v3.py
│   ├── churn/
│   │   ├── churn.py
│   │   ├── churn_v2.py
│   │   └── churn_v3.py
│   └── profitability/
│       └── profitability.py
│
├── main.py
├── requirements.txt
└── README.md
```

## 6. Ejecución

### Requisitos

- Python 3.13+
- pandas
- numpy
- pyarrow
- openpyxl
- scikit-learn
- statsmodels
- duckdb
- matplotlib

### Crear y activar el entorno virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Instalar dependencias

```powershell
pip install -r requirements.txt
```

Si no existe `requirements.txt`:

```powershell
pip install pandas numpy pyarrow openpyxl scikit-learn statsmodels duckdb matplotlib
```

### Ejecutar el pipeline completo

```powershell
python main.py
```

## 7. Principales reglas de integración

### Eurolam — Polonia

- Se eliminaron 1,810 repeticiones derivadas de transacciones históricas reprocesadas.
- La deduplicación comparó los campos comerciales e ignoró únicamente `record_key` y `source_file`.
- Las correcciones comerciales se conservaron cuando existían diferencias reales.
- Las facturas se trataron con signo positivo y las `KOREKTA` con signo negativo.

### Indabel — Bélgica

- `FKDAT` se interpretó explícitamente como fecha `YYYYMMDD`.
- `MENGE` estaba expresado en kilogramos.

```text
toneladas = kilogramos / 1,000
```

- `ZF2` se trató como factura.
- `ZG2` se trató como nota de crédito.
- Los códigos SAP con ceros iniciales se normalizaron:

```text
0000000000ADE-1000 → ADE-1000
```

### Turio — España

- Se detectó la fila real de encabezado en los Excel.
- Se eliminaron 10 duplicados después de revisar diferencias comerciales.
- Las unidades se transformaron a toneladas:

```text
toneladas = unidades × kg por unidad / 1,000
```

- Cuando faltaba `Importe Base (€)`, se reconstruyó como:

```text
Importe Base = Importe Total / 1.21
```

Este cálculo supone un IVA de 21% y debe validarse con Finanzas en producción.

### Tipos de cambio

El maestro expresa unidades de moneda local por 1 EUR.

```text
venta EUR = importe local / tipo de cambio
```

Se imputaron 4,020 filas mediante interpolación temporal. Estas observaciones quedaron identificadas con `fx_was_imputed`.

## 8. Modelo canónico

Archivo principal:

```text
data/curated/fact_sales_canonical.parquet
```

Resultados:

- 225,044 transacciones únicas.
- 903 identificadores globales de cliente.
- 38 productos globales.
- Periodo: enero de 2024 a junio de 2026.
- 0 llaves duplicadas.
- 0 ventas sin conversión a EUR.
- 0 ventas sin costo estándar.
- 0 clientes o productos finales sin homologación.

Resultados históricos de cliente final:

- Venta neta: **€280.67 M**
- Volumen: **291.27 kt**
- Margen bruto: **€30.73 M**
- Margen bruto: **10.95%**

## 9. Cifras de control

Archivos:

```text
outputs/cifras-control.csv
outputs/executive_metrics.csv
outputs/top_countries_2025.csv
outputs/intercompany_summary.csv
```

### Resultados 2025

- Venta neta cliente final: **€117.58 M**
- Volumen: **120.96 kt**
- Margen bruto: **€12.71 M**
- Margen bruto: **10.81%**

### Resultados 2026-S1

- Venta neta: **€63.38 M**
- Volumen: **63.96 kt**
- Clientes activos: **816**

### Top países 2025

| País | Venta | Margen |
|---|---:|---:|
| Polonia | €26.63 M | 14.97% |
| España | €17.07 M | 10.52% |
| Francia | €12.00 M | 5.95% |

## 10. Forecast

### Forecast V1

Modelos comparados:

- Seasonal Naive.
- Tendencia lineal.
- ETS / Holt-Winters.

Validación:

- entrenamiento hasta junio de 2025 y validación de H2-2025;
- entrenamiento hasta diciembre de 2025 y validación de H1-2026.

Métricas:

- WAPE;
- MAE;
- RMSE;
- Bias.

La evidencia de backtesting es preliminar debido a que solo existen 30 meses de historia.

### Forecast V2

```text
Revenue = volumen × precio medio
```

Forecast base H2-2026:

- Volumen: **58,404.84 t**
- Revenue: **€58.53 M**
- Precio medio ponderado: **€1,002.09/t**

Los intervalos reportados son intervalos empíricos aproximados del 95% basados en residuos del backtesting. No deben interpretarse como probabilidades exactas.

### Forecast V3 — Scenario Planning

| Escenario | Volumen | Precio | Revenue |
|---|---:|---:|---:|
| Pesimista | -5% | -2% | €54.49 M |
| Base | 0% | 0% | €58.53 M |
| Optimista | +5% | +2% | €62.68 M |

V3 es un análisis de sensibilidad comercial, no un nuevo modelo estadístico.

## 11. Customer Health

No existía una etiqueta histórica explícita de abandono, por lo que no se entrenó un modelo supervisado de churn.

Se construyó un índice compuesto por:

- 30% recencia;
- 25% tendencia de ventas;
- 20% tendencia de frecuencia;
- 15% cambio de margen;
- 10% amplitud del portafolio.

| Estado | Clientes |
|---|---:|
| Critical | 101 |
| High Risk | 204 |
| Watch | 380 |
| Healthy | 188 |

El score no representa una probabilidad calibrada de churn. Es un indicador relativo de deterioro comercial.

Archivos:

```text
outputs/customer_health_index.csv
outputs/customer_health_summary.csv
outputs/customer_health_actions.csv
```

## 12. Recovery Priority

Se creó un ranking continuo mediante:

- 45% valor económico en riesgo;
- 35% riesgo de churn;
- 20% margen positivo recuperable.

Archivo:

```text
outputs/customer_recovery_priority.csv
```

### Limitación

Los umbrales fijos no separaron adecuadamente la población:

- 2 clientes en `MEDIUM`;
- 871 en `MONITOR`;
- 0 en `HIGH`;
- 0 en `IMMEDIATE`.

El ranking continuo es útil, pero las categorías deben recalibrarse mediante percentiles o según la capacidad del equipo comercial.

## 13. Margin Intelligence

Se cuantificaron cuatro palancas sobre el Forecast V2 de H2-2026:

| Palanca | Impacto estimado |
|---|---:|
| Recuperar cuentas de margen bajo o negativo | €318.7 mil |
| Pricing selectivo | €270.5 mil |
| Reducir notas de crédito | €14.4 mil |
| Mejorar el mix | €14.2 mil |
| **Total** | **€617.7 mil** |

Base utilizada:

```text
Forecast V2 H2-2026 = €58.53 M
```

Impacto equivalente:

```text
€617.7 mil / €58.53 M = +1.06 pp
```

Gap frente al objetivo:

```text
+2.00 pp - +1.06 pp = +0.94 pp
```

Las palancas comerciales cuantificadas cubren poco más de la mitad del objetivo. El gap restante requiere compras, reducción de costos, eficiencia productiva y logística, o pricing basado en elasticidad.

El potencial de €617.7 mil debe interpretarse como potencial bruto. Antes de ejecución se deben validar posibles solapamientos entre pricing selectivo y recuperación de cuentas.

## 14. Decisiones recomendadas

### 0–3 meses

- Implementar pricing selectivo.
- Intervenir cuentas de margen bajo o negativo.
- Reducir causas de notas de crédito.

### 3–6 meses

- Optimizar el mix de productos.
- Monitorear Customer Health mensualmente.
- Medir el impacto real sobre el margen.

### 6–12 meses

- Integrar iniciativas de compras y eficiencia operativa.
- Actualizar el forecast mensualmente.
- Recalibrar el plan para cerrar los +0.94 pp restantes.

## 15. Supuestos

- IVA de 21% para reconstruir `Importe Base (€)` en Turio.
- Interpolación temporal de tipos de cambio faltantes.
- Pesos de Customer Health definidos como reglas de negocio.
- Escenarios V3 definidos mediante sensibilidades de volumen y precio.
- Impacto de margen cuantificado sobre H2-2026, no sobre 12 meses completos.
- Las palancas de rentabilidad fueron calculadas inicialmente de forma independiente.

## 16. Limitaciones

- Solo existen 30 meses de historia para forecasting.
- El backtesting utiliza dos ventanas de seis meses.
- No existe una etiqueta histórica confirmada de churn.
- Recovery Priority requiere recalibración.
- El objetivo es de 12 meses, pero la cuantificación utiliza el forecast disponible de seis meses.
- No se estimó elasticidad de precio.
- No se cuantificó el solapamiento entre palancas.
- El supuesto de IVA debe validarse con Finanzas.
- Debe analizarse la concentración de FX imputado por país y periodo.

## 17. Mejoras futuras

- Automatizar la ingesta mediante un scheduler.
- Implementar pruebas unitarias y de regresión de datos.
- Publicar dashboards en Power BI o Tableau.
- Extender el forecast a 12 meses.
- Incorporar nuevas ventanas de backtesting conforme exista más historia.
- Calibrar Customer Health contra abandono real.
- Estimar elasticidades de precio.
- Integrar costos de producción, compras y logística.
- Desplegar el modelo en nube.
- Crear alertas automáticas para cuentas críticas y desviaciones de forecast.

## 18. Principales archivos de salida

```text
outputs/
├── cifras-control.csv
├── executive_metrics.csv
├── top_countries_2025.csv
├── intercompany_summary.csv
├── forecast_2026_s2.csv
├── forecast_backtesting.csv
├── forecast_v2_2026_s2.csv
├── forecast_v2_backtesting.csv
├── forecast_v2_summary.csv
├── forecast_v3_scenarios.csv
├── forecast_v3_scenario_summary.csv
├── churn_prioritized.csv
├── churn_summary.csv
├── customer_health_index.csv
├── customer_health_summary.csv
├── customer_health_actions.csv
├── customer_recovery_priority.csv
├── customer_recovery_priority_summary.csv
├── profitability_scenarios.csv
└── profitability_customer_opportunities.csv
```

## 19. Conclusión

El principal valor del proyecto no reside únicamente en los modelos analíticos.

La solución primero construye una única versión confiable de las ventas del grupo y, sobre esa base, permite:

- anticipar demanda, precio e ingresos;
- detectar deterioro comercial;
- priorizar acciones por impacto económico;
- cuantificar oportunidades de margen;
- monitorear el avance hacia el objetivo corporativo.

La plataforma convierte datos provenientes de tres ERPs en decisiones comerciales medibles y escalables.

## Decisiones tecnológicas

Se eligió Python y pandas por la heterogeneidad de las fuentes de
origen —Parquet, CSV y Excel— y por la necesidad de aplicar reglas de
negocio específicas para cada ERP.

Parquet se utilizó como formato intermedio y curado debido a su tipado,
compresión y eficiencia de lectura. El proyecto se estructuró en capas
de ingesta, transformación, reporting y analítica, coordinadas desde
un único punto de entrada (`main.py`).

La arquitectura permite migrar posteriormente las transformaciones a
dbt, Spark o un data warehouse sin modificar las definiciones centrales
de ventas, volumen, margen, clientes y productos.

## Uso de asistentes de inteligencia artificial

Se utilizaron ChatGPT y Claude como herramientas de apoyo para revisar
la estructura del proyecto, contrastar decisiones metodológicas,
documentar supuestos y generar borradores iniciales de algunos
fragmentos de código.

Todas las reglas de negocio, transformaciones, validaciones, resultados
y decisiones finales fueron revisadas y ejecutadas por la autora.

## Tratamiento de eventos atípicos

No se eliminaron observaciones únicamente por presentar valores
extremos. Primero se distinguieron errores técnicos —duplicados,
fechas mal interpretadas, unidades inconsistentes y signos incorrectos—
de eventos comerciales reales.

Los errores confirmados fueron corregidos durante la limpieza. Los
picos comerciales plausibles se conservaron para evitar suavizar
artificialmente la demanda. El backtesting se reportó sobre ventanas
temporales completas, sin retirar periodos desfavorables.

## Definición de riesgo de abandono

La fuente no contenía una etiqueta histórica explícita de abandono.
Por ello se implementó un Customer Health Index como baseline
explicable de deterioro comercial.

El índice utiliza recencia, tendencia de ventas, cambio de frecuencia,
margen y amplitud del portafolio. No representa una probabilidad
calibrada de churn.

En producción se recomienda construir snapshots históricos y definir
churn como la ausencia de compras durante los 120 días posteriores a
una fecha de corte, evaluando el modelo mediante separación temporal,
PR-AUC, lift y precision en el grupo priorizado.


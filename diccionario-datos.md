# Diccionario de datos — ADE Group

> Nota de la Dirección de Datos: esta es la documentación que existe hoy en el grupo.
> Algunas fuentes están mejor documentadas que otras. Donde haya huecos, aplica tu
> criterio y documenta tus supuestos.

## erp-indabel-belgica/ (SAP · parquet)

`indabel_vbrp_2024.parquet`, `indabel_vbrp_2025.parquet`, `indabel_vbrp_2026_S1.parquet`
— líneas de facturación (tablas VBRK/VBRP combinadas).

| Columna | Descripción |
|---|---|
| VBELN | Número de documento de facturación |
| POSNR | Posición (línea) del documento |
| FKART | Clase de documento. `ZF2` = factura. `ZG2` = abono (nota de crédito) |
| FKDAT | Fecha de facturación |
| KUNNR | Código de cliente |
| NAME1 / LAND1 | Nombre y país del cliente |
| MATNR / ARKTX | Código y descripción de material |
| MENGE / MEINS | Cantidad y unidad de medida |
| WAERK | Moneda del documento |
| NETWR | Valor neto de la posición en moneda del documento |
| SHKZG | Indicador debe/haber |
| BSTNK | Referencia de pedido del OMS |
| VGBEL | Documento de referencia (en abonos) |

`indabel_clientes.parquet` — maestro de clientes SAP (KUNNR, NAME1, LAND1, STCD1 = NIF/VAT,
KDGRP = grupo de clientes, WAERS = moneda).

## erp-eurolam-polonia/ (StalexERP v7.3 · csv)

`faktury_2024.csv`, `faktury_2025.csv`, `faktury_2026_S1.csv` — facturación.
`klienci.csv` — maestro de clientes.

La documentación original de StalexERP está en polaco y está incompleta; traducción
parcial del equipo local:

| Columna | Descripción |
|---|---|
| NR_FAKTURY / POZYCJA | Nº de factura / línea |
| DATA_FAKTURY | Fecha de factura |
| KOD_KLIENTA / NAZWA_KLIENTA / KRAJ | Código, nombre y país del cliente |
| INDEKS / NAZWA_TOWARU | Código y nombre de artículo |
| ILOSC_TON | Cantidad |
| CENA_NETTO_T / WARTOSC_NETTO | Precio y valor neto |
| WALUTA | Moneda |
| RODZAJ | Tipo de documento (FAKTURA / KOREKTA) |
| NR_ZAMOWIENIA | Referencia de pedido del OMS |

En `klienci.csv`: NIP = NIF/VAT, SEGMENT = segmento comercial.

> Aviso del equipo de TI de Zawiercie: "el exportador de StalexERP a veces re-procesa
> lotes cuando el job nocturno falla; el archivo resultante es el que hay".

## erp-turio-espana/ (GestionMax · xlsx)

Un informe mensual por archivo (ene-2024 → jun-2026). El nombre de archivo y de hoja
lo define el usuario que genera el informe cada mes. Columnas del informe: número de
factura, línea, fecha, cliente, artículo (código GestionMax `GM-xxxx`), descripción,
cantidad en **unidades de venta** (paneles, rollos, bobinas, cajas), importes y
referencia de pedido.

`clientes-turio.xlsx` — maestro de clientes de la filial.

> Changelog GestionMax v4.2 (dic-2024): "se actualiza la configuración de columnas de
> importes del informe mensual de ventas". v4.7 (jul-2025): "se restaura la
> configuración anterior de columnas a petición de los usuarios".

## oms-pedidos/ (parquet)

`pedidos_oms.parquet` — líneas de pedido del Order Management System central:
`pedido_id`, `linea_pedido`, `fecha_pedido`, `anio_mes`, `filial`, `id_cliente_erp`,
`sku` (código de grupo `ADE-xxxx`), `unidades_pedidas`, `estado`
(`COMPLETO` / `PARCIAL` / `CANCELADO`).

## maestros/

| Archivo | Contenido |
|---|---|
| `productos.xlsx` | Hoja `productos`: sku de grupo, nombre, familia, **kg por unidad de venta**, unidad. Hoja `equivalencias-turio`: mapeo código GestionMax ↔ sku de grupo |
| `costos-estandar.xlsx` | Costo estándar EUR/ton por sku, planta y año |
| `tipos-cambio.csv` | Tipo de cambio mensual (unidades de moneda por 1 EUR) |
| `comerciales-territorios.csv` | Asignación de comerciales a países con vigencias |
| `crm-clientes.csv` | Vista de clientes del CRM corporativo (id global, filial, id en el ERP, VAT, segmento, estatus) |

Familias de producto: MEL (malla electrosoldada), MHX (malla hexagonal), AGV (alambre
galvanizado), APU (alambre de púas), CGN (cerca ganadera), CLV (clavos y grapas),
SEM (semiterminados).

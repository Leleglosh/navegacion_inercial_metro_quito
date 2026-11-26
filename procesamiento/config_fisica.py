"""Constantes fisicas del proyecto de navegacion inercial (Quito, Ecuador).

Distinguir:
- g_estandar: conversion de unidades "g" (ficha tecnica del sensor) a m/s2.
- g_local: gravedad real de referencia para experimentos en Quito.

Referencia para g_estandar: NIST, aceleracion estandar de gravedad.
El valor local 9.7726 m/s2 es la referencia elegida por el equipo;
registrar fuente y ubicacion aproximada en los metadatos.
"""

GRAVEDAD_ESTANDAR_MS2 = 9.80665
GRAVEDAD_QUITO_MS2 = 9.7726

SENSIBILIDAD_ACEL_CUENTAS_POR_G = 16384.0  # MPU-6500, +/- 2 g
SENSIBILIDAD_GIRO_CUENTAS_POR_DPS = 131.0  # MPU-6500, +/- 250 grados/s


# Proyecto de Navegación Inercial — Metro de Quito

## Descripción

Proyecto desarrollado para la asignatura de Métodos Numéricos.

El objetivo es construir un dispositivo capaz de registrar aceleración, velocidad angular y presión atmosférica para estimar velocidad y posición sin utilizar GPS.

## Integrantes

- Integrante 1: Stephanie Lozada
- Integrante 2: Kevin Arce
- Integrante 3: Ariel Soria
- Integrante 4:

## Hardware

- ESP32 WROOM-32D
- Sensor GY-91
- Módulo lector microSD SPI
- Tarjeta microSD de 16 GB
- Pulsador
- Protoboard y cables Dupont

## Software

- Arduino IDE y C++
- Python
- Git y GitHub

## Metodología

1. Adquisición de datos crudos.
2. Verificación de frecuencia y marcas de tiempo.
3. Caracterización y calibración de los sensores.
4. Integración numérica.
5. Estimación de velocidad y posición.
6. Comparación con referencias experimentales.

## Estado del proyecto

Primer parcial: ensamblaje, adquisición de datos, caracterización y primeras validaciones.

## Organización

- `firmware/`: programas del ESP32.
- `procesamiento/`: programas de Python.
- `datos/`: registros experimentales.
- `resultados/`: gráficas y tablas.
- `bitacora/`: seguimiento de actividades.
- `documentacion/`: conexiones y fotografías.
- `presentacion/`: materiales de exposición.

## Uso de inteligencia artificial

Se documentará en `bitacora/uso_ia.md`, incluyendo las sugerencias utilizadas, su verificación y los errores detectados.

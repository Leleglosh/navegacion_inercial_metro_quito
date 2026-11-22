"""
PIPELINE PRINCIPAL DE PROCESAMIENTO DE DATOS INERCIALES

Este script integra todos los módulos de la carpeta 'procesamiento/':
1. Carga los datos (CSV de serial o .BIN de microSD).
2. Convierte a unidades físicas (m/s², °/s).
3. Aplica calibración de sesgo y escala.
4. Resta la gravedad local de Quito.
5. Realiza la integración numérica (Euler y Trapecio).
6. Genera y guarda las gráficas de resultados.
"""

import os
import pandas as pd
import numpy as np

# Importar los módulos desarrollados en la carpeta procesamiento
from lectura_datos import cargar_csv_serial, cargar_binario_sd, convertir_a_unidades_fisicas
from calibracion import calibrar_giroscopio, calibrar_acelerometro_6_caras, aplicar_calibracion
from integracion import remover_gravedad_estatica, comparar_metodos_integracion
from graficas import graficar_sensores_raw, graficar_integracion


def ejecutar_pipeline(ruta_archivo, es_binario=False):
    """
    Ejecuta el flujo completo de procesamiento sobre un archivo de datos.
    
    Parámetros:
        ruta_archivo (str): Ruta al archivo de entrada (.csv o .BIN).
        es_binario (bool): True si es archivo binario de la SD, False si es CSV.
    """
    print(f"=== Iniciando Pipeline para: {ruta_archivo} ===")
    
    # 1. Cargar datos crudos
    if es_binario:
        df_raw = cargar_binario_sd(ruta_archivo)
    else:
        df_raw = cargar_csv_serial(ruta_archivo)
        
    # 2. Conversión a unidades físicas (m/s² y deg/s)
    df_fisico = convertir_a_unidades_fisicas(df_raw, g_quito=9.780)
    
    # 3. Estimación de parámetros de calibración (ejemplo con valores base)
    # OBSERVACIÓN FUTURA: Cuando tengan los datos del experimento de las 6 caras,
    # reemplacen estos valores por la lectura de las caras reales. $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ CAMBIAR
    bias_gyro = calibrar_giroscopio(df_fisico)
    bias_accel = np.array([0.0, 0.0, 0.0])
    escala_accel = np.array([1.0, 1.0, 1.0])
    
    df_calibrado = aplicar_calibracion(df_fisico, bias_gyro, bias_accel, escala_accel)
    
    # 4. Remover gravedad estática de Quito (9.780 m/s²)
    # Asumiendo que el sensor mide aprox. -9.780 m/s² en Z estático
    df_calibrado['az_neta'] = remover_gravedad_estatica(df_calibrado['az'], g_quito=9.780)
    
    # 5. Integración Numérica (Euler y Trapecio)
    df_procesado = comparar_metodos_integracion(df_calibrado, columna_accel='az_neta')
    
    # 6. Guardado de datos procesados en CSV dentro de resultados/
    os.makedirs("resultados", exist_ok=True)
    ruta_salida_csv = "resultados/datos_procesados.csv"
    df_procesado.to_csv(ruta_salida_csv, index=False)
    print(f"[OK] Datos procesados guardados en: {ruta_salida_csv}")
    
    # 7. Generación de Gráficas
    graficar_sensores_raw(df_procesado, ruta_guardado="resultados/sensores_unidades_fisicas.png")
    graficar_integracion(df_procesado, ruta_guardado="resultados/perfil_cinematica.png")
    
    print("=== Pipeline ejecutado con éxito ===")


if __name__ == "__main__":
    print("--- Prueba rápida con datos sintéticos ---")
    
    # Simulación de un archivo CSV temporal para verificar la integración total
    csv_prueba = "prueba_pipeline.csv"
    t_us_inicial = 44861950
    dt_us = 10000  # 100 Hz
    
    filas = ["t_us,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,p_raw,t_raw"]
    for i in range(100):
        t_us = t_us_inicial + i * dt_us
        az_val = -15858 + int(500 * np.sin(2 * np.pi * i / 50))
        filas.append(f"{t_us},712,142,{az_val},-46,67,13,479888,534000")
        
    with open(csv_prueba, "w") as f:
        f.write("\n".join(filas))
        
    # Ejecutar pipeline
    ejecutar_pipeline(csv_prueba, es_binario=False)
    
    # Limpiar archivo temporal de prueba
    if os.path.exists(csv_prueba):
        os.remove(csv_prueba)

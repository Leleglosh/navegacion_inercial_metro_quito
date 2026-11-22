"""
Este script implementa:
1. Calibración de Giroscopio (Zero-Rate Offset / Sesgo en reposo).
2. Calibración de Acelerómetro mediante el Método de las 6 Caras (Mínimos Cuadrados).
3. Aplicación de los parámetros calculados a nuevos conjuntos de datos.
"""

import numpy as np
import pandas as pd

def calibrar_giroscopio(df_reposo):
    """
    Calcula el sesgo (bias) estático del giroscopio a partir de un registro en reposo.
    Parámetros:
        df_reposo (pd.DataFrame): DataFrame que contiene las columnas 'gx', 'gy', 'gz'
                                  (en grados/segundo o en LSB crudos).
    Retorna:
        bias_g (np.array): Arreglo de 3 elementos con los offsets [bias_gx, bias_gy, bias_gz].
    """
    # Se calcula la media de cada eje mientras el sensor estuvo completamente inmóvil.
    # En un giroscopio ideal, el valor promedio en reposo debería ser 0 dps.
  
    bias_gx = df_reposo['gx'].mean()
    bias_gy = df_reposo['gy'].mean()
    bias_gz = df_reposo['gz'].mean()
    bias_g = np.array([bias_gx, bias_gy, bias_gz])

    # El sesgo del giroscopio varía ligeramente con la temperatura.
    # Si en las pruebas del metro o ascensor la temperatura cambia mucho, 
    # se recomienda recalcular este bias usando muestras de reposo tomadas justo antes de mover el dispositivo.
    return bias_g

def calibrar_acelerometro_6_caras(promedios_caras, g_local=1.0):
    """
    Calcula la matriz de escala (S) y el vector de bias (b) para el acelerómetro
    usando las 6 posiciones estáticas (una por cada cara de la caja).
    
    Modelo físico: a_medida = S * a_real + b  =>  a_real = S^-1 * (a_medida - b)
    
    Parámetros:
        promedios_caras (dict o np.array): Arreglo de forma (6, 3) con el valor promedio 
                                           medido [ax, ay, az] en cada una de las 6 caras.
        g_local (float): Valor de referencia de la gravedad. 
                         - Usar 1.0 si los datos están en unidades de 'g'.
                         - NOTA QUITO: Si los datos están en m/s^2, ajustar g_local = 9.780 m/s^2
                           (la aceleración de la gravedad estándar en Quito debido a la altitud).
    
    Retorna:
        bias_a (np.array): Vector de sesgos [b_x, b_y, b_z] (3,)
        escala_a (np.array): Vector de factores de escala [s_x, s_y, s_z] (3,)
    """
    # promedios_caras debe ser una matriz de 6 filas y 3 columnas.
    # Ejemplo de filas: [+X arriba, -X arriba, +Y arriba, -Y arriba, +Z arriba, -Z arriba]
    medidos = np.asarray(promedios_caras)
    
    # Matriz ideal esperada para las 6 caras en orden (+X, -X, +Y, -Y, +Z, -Z):
    # AJUSTAR ESTE ORDEN FUTURO: Si el orden en el que graban las 6 caras cambia en la práctica,
    # deben reordenar las filas de esta matriz 'ideales' para que coincida exactamente.
    ideales = np.array([
        [ g_local,  0.0,      0.0],     # Cara +X hacia arriba
        [-g_local,  0.0,      0.0],     # Cara -X hacia arriba
        [ 0.0,      g_local,  0.0],     # Cara +Y hacia arriba
        [ 0.0,     -g_local,  0.0],     # Cara -Y hacia arriba
        [ 0.0,      0.0,      g_local], # Cara +Z hacia arriba
        [ 0.0,      0.0,     -g_local]  # Cara -Z hacia arriba
    ])
    
    bias_a = np.zeros(3)
    escala_a = np.ones(3)
    
    # Ajuste lineal independiente por cada eje: y_medido = escala * x_ideal + bias
    for i in range(3):
        # Mínimos cuadrados para encontrar escala (m) y bias (c): medido = m * ideal + c
        A = np.vstack([ideales[:, i], np.ones(6)]).T
        m, c = np.linalg.lstsq(A, medidos[:, i], rcond=None)[0]
        
        escala_a[i] = m
        bias_a[i] = c
        
    # NOTA FUTURA SOBRE DESALINEAMIENTO (CROSS-AXIS):
    # Este cálculo asume ejes ortogonales. Si existe un desacople severo entre ejes por montaje en protoboard,
    # se requerirá resolver una matriz completa de 3x3 en lugar de 3 valores independientes de escala.
    
    return bias_a, escala_a
  
def aplicar_calibracion(df_raw, bias_g, bias_a, escala_a, LSB_accel=16384.0, LSB_gyro=131.0):
    """
    Recibe un DataFrame con lecturas crudas y aplica la corrección de sesgo y escala.
    
    Parámetros:
        df_raw (pd.DataFrame): Datos crudos leídos del archivo .BIN o CSV.
        bias_g (np.array): Offsets del giroscopio.
        bias_a (np.array): Offsets del acelerómetro.
        escala_a (np.array): Factores de escala del acelerómetro.
        LSB_accel (float): Factor de sensibilidad del acelerómetro según la escala configurada.
                           - ±2g  : 16384 LSB/g (valor por defecto)
                           - ±4g  : 8192 LSB/g
                           - ±8g  : 4096 LSB/g
                           - ±16g : 2048 LSB/g
        LSB_gyro (float): Factor de sensibilidad del giroscopio según escala.
                          - ±250 dps  : 131.0 LSB/(deg/s) (valor por defecto)
                          - ±500 dps  : 65.5 LSB/(deg/s)
                          - ±1000 dps : 32.8 LSB/(deg/s)
                          - ±2000 dps : 16.4 LSB/(deg/s)
    
    Retorna:
        df_cal (pd.DataFrame): DataFrame con las mediciones en unidades físicas procesadas.
    """
    df_cal = df_raw.copy()
    
    # 1. Convertir datos de LSB crudos a unidades físicas iniciales (si vienen crudos int16)
    # AJUSTE FUTURO: Si 'lectura_datos.py' ya hace la división por LSB, omitir estas dos divisiones.
    if 'ax_raw' in df_cal.columns:
        df_cal['ax'] = df_cal['ax_raw'] / LSB_accel
        df_cal['ay'] = df_cal['ay_raw'] / LSB_accel
        df_cal['az'] = df_cal['az_raw'] / LSB_accel
        df_cal['gx'] = df_cal['gx_raw'] / LSB_gyro
        df_cal['gy'] = df_cal['gy_raw'] / LSB_gyro
        df_cal['gz'] = df_cal['gz_raw'] / LSB_gyro

    # 2. Corregir Giroscopio: Restar el sesgo estático (dps)
    df_cal['gx_corregido'] = df_cal['gx'] - bias_g[0]
    df_cal['gy_corregido'] = df_cal['gy'] - bias_g[1]
    df_cal['gz_corregido'] = df_cal['gz'] - bias_g[2]

    # 3. Corregir Acelerómetro: Aplicar fórmula (Medido - Bias) / Escala
    df_cal['ax_corregido'] = (df_cal['ax'] - bias_a[0]) / escala_a[0]
    df_cal['ay_corregido'] = (df_cal['ay'] - bias_a[1]) / escala_a[1]
    df_cal['az_corregido'] = (df_cal['az'] - bias_a[2]) / escala_a[2]

    return df_cal

if __name__ == "__main__":
    print("--- Ejecutando prueba autónoma de calibracion.py ---")
    
    # Simulación de datos en reposo para giroscopio
    data_reposo = {
        'gx': np.random.normal(0.5, 0.1, 1000),  # Bias sintético de +0.5 dps en X
        'gy': np.random.normal(-0.2, 0.1, 1000), # Bias sintético de -0.2 dps en Y
        'gz': np.random.normal(0.1, 0.1, 1000)   # Bias sintético de +0.1 dps en Z
    }
    df_reposo_test = pd.DataFrame(data_reposo)
    
    bias_gyro = calibrar_giroscopio(df_reposo_test)
    print(f"Bias de Giroscopio calculado (dps): X={bias_gyro[0]:.4f}, Y={bias_gyro[1]:.4f}, Z={bias_gyro[2]:.4f}")
    
    # Simulación de las 6 caras con 5% de error de escala y offset
    # Caras: [+X, -X, +Y, -Y, +Z, -Z]
    caras_simuladas = np.array([
        [ 1.02,  0.01, -0.01],
        [-0.98,  0.01, -0.01],
        [ 0.01,  1.05, -0.01],
        [ 0.01, -0.95, -0.01],
        [ 0.01,  0.01,  0.99],
        [ 0.01,  0.01, -1.01]
    ])
    
    # Calibrar acelerómetro para Quito (g_local = 1.0 si se trabaja en 'g')
    bias_accel, escala_accel = calibrar_acelerometro_6_caras(caras_simuladas, g_local=1.0)
    print(f"Bias Acelerómetro (g): {bias_accel}")
    print(f"Factores de Escala Acelerómetro: {escala_accel}")

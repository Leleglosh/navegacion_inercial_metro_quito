"""
Este script implementa:
1. Lectura de datos impresos por puerto serie en formato CSV (pruebas iniciales).
2. Decodificación de archivos binarios (.BIN) de 36 bytes guardados en la tarjeta microSD.
3. Conversión de magnitudes crudas a unidades físicas (m/s², deg/s, Pa, °C).
"""
import os
import numpy as np
import pandas as pd

# 1. ESTRUCTURA BINARIA EXACTA DE 36 BYTES (FIRMWARE ESP32)
# Define la disposición exacta de los bytes grabados en el archivo LOGnnnn.BIN.
# Usamos tipos Little-Endian ('<') coincidiendo con la arquitectura del ESP32.
ESTRUCTURA_BINARIA = np.dtype([
    ('t_us', '<u4'),      # Marca de tiempo en microsegundos (uint32) - 4 bytes
    ('seq', '<u2'),       # Número de secuencia de muestra (uint16) - 2 bytes
    ('flags', 'u1'),      # Banderas (baro, mag, btn_state, btn_edge, overrun) - 1 byte
    ('rsv', 'u1'),        # Byte reservado para alineación en memoria - 1 byte
    ('a', '<i2', (3,)),   # Aceleración cruda int16 [ax, ay, az] - 6 bytes
    ('g', '<i2', (3,)),   # Giroscopio crudo int16 [gx, gy, gz] - 6 bytes
    ('m', '<i2', (3,)),   # Magnetómetro crudo int16 [mx, my, mz] - 6 bytes
    ('t_mpu', '<i2'),     # Temperatura del sensor inercial int16 - 2 bytes
    ('p_raw', '<i4'),     # Presión atmosférica cruda int32 - 4 bytes
    ('t_raw', '<i4')      # Temperatura del barómetro cruda int32 - 4 bytes
])

def cargar_csv_serial(ruta_csv):
    """
    Lee un archivo CSV obtenido mediante el Monitor Serie de Arduino IDE.
    Parámetros:
        ruta_csv (str): Ruta al archivo .csv o .txt guardado.
        
    Retorna:
        pd.DataFrame: Datos cargados con marcas de tiempo relativas en segundos.
    """
    # Se omiten las líneas de comentario que inicien con '#' generadas por el firmware
    df = pd.read_csv(ruta_csv, comment='#')
    
    # Limpiar posibles espacios en los nombres de las columnas
    df.columns = df.columns.str.strip()
    
    # Calcular el tiempo relativo en segundos (t_s) a partir del primer t_us grabado
    if 't_us' in df.columns:
        df['t_s'] = (df['t_us'] - df['t_us'].iloc[0]) / 1e6
    return df

def cargar_binario_sd(ruta_bin):
    """
    Lee y decodifica un archivo binario (.BIN) grabado en la memoria microSD por el ESP32.
    Parámetros:
        ruta_bin (str): Ruta completa al archivo .BIN (ej. 'datos/LOG0000.BIN'). 
    Retorna:
        pd.DataFrame: Registro completo decodificado en columnas de DataFrame.
    """
    if not os.path.exists(ruta_bin):
        raise FileNotFoundError(f"No se encontró el archivo binario en: {ruta_bin}")
        
    # Lectura ultrarrápida del bloque binario completo utilizando NumPy
    datos = np.fromfile(ruta_bin, dtype=ESTRUCTURA_BINARIA)
    
    df = pd.DataFrame()
    df['t_us'] = datos['t_us']
    # Calcular tiempo en segundos desde la primera muestra
    df['t_s'] = (datos['t_us'] - datos['t_us'][0]) / 1e6
    df['seq'] = datos['seq']
    df['flags'] = datos['flags']
    
    # Descomponer arreglo de 3 ejes del acelerómetro
    df['ax_raw'] = datos['a'][:, 0]
    df['ay_raw'] = datos['a'][:, 1]
    df['az_raw'] = datos['a'][:, 2]
    
    # Descomponer arreglo de 3 ejes del giroscopio
    df['gx_raw'] = datos['g'][:, 0]
    df['gy_raw'] = datos['g'][:, 1]
    df['gz_raw'] = datos['g'][:, 2]
    
    # Descomponer arreglo del magnetómetro (si aplica)
    df['mx_raw'] = datos['m'][:, 0]
    df['my_raw'] = datos['m'][:, 1]
    df['mz_raw'] = datos['m'][:, 2]
    
    # Presión y temperatura crudas del barómetro BMP280
    df['p_raw'] = datos['p_raw']
    df['t_raw'] = datos['t_raw']
    
    # Decodificar el estado del pulsador a partir de las banderas (bit 2 y bit 3)
    # BIT 2: Estado continuo del botón (0: Presionado, 1: Suelto por INPUT_PULLUP)
    # BIT 3: Evento de flanco/pulsación (1 si fue pulsado en ese ciclo)
    df['btn_state'] = (datos['flags'] >> 2) & 0x01
    df['btn_edge'] = (datos['flags'] >> 3) & 0x01
    
    # NOTA FUTURA SOBRE OVERRUN:
    # El bit 4 (datos['flags'] >> 4) indica si hubo pérdida de muestras en la tarjeta SD.
    df['overrun'] = (datos['flags'] >> 4) & 0x01
    
    return df

def convertir_a_unidades_fisicas(df, lsb_accel=16384.0, lsb_gyro=131.0, g_quito=9.780):
    """
    Convierte las lecturas digitales crudas a unidades físicas estándar:
    - Aceleración: de LSB a m/s² (usando g local de Quito ≈ 9.780 m/s²)
    - Giroscopio: de LSB a °/s (grados por segundo)
    Parámetros:
        df (pd.DataFrame): DataFrame con las columnas 'ax_raw', 'gx_raw', etc.
        lsb_accel (float): Factor de sensibilidad del acelerómetro (16384.0 para ±2g).
        lsb_gyro (float): Factor de sensibilidad del giroscopio (131.0 para ±250 dps).
        g_quito (float): Gravedad local de Quito en m/s² (default: 9.780).     
    Retorna:
        pd.DataFrame: Copia del DataFrame con columnas adicionales de magnitudes físicas.
    """
    df_fisico = df.copy()
    
    # Conversión Acelerómetro (LSB -> g -> m/s²)
    if 'ax_raw' in df_fisico.columns:
        df_fisico['ax'] = (df_fisico['ax_raw'] / lsb_accel) * g_quito
        df_fisico['ay'] = (df_fisico['ay_raw'] / lsb_accel) * g_quito
        df_fisico['az'] = (df_fisico['az_raw'] / lsb_accel) * g_quito
        
    # Conversión Giroscopio (LSB -> deg/s)
    if 'gx_raw' in df_fisico.columns:
        df_fisico['gx'] = df_fisico['gx_raw'] / lsb_gyro
        df_fisico['gy'] = df_fisico['gy_raw'] / lsb_gyro
        df_fisico['gz'] = df_fisico['gz_raw'] / lsb_gyro
        
    return df_fisico

if __name__ == "__main__":
    print("--- Ejecutando prueba autónoma de lectura_datos.py ---")
    
    # 1. Simular una fila de datos idéntica a la obtenida en el Monitor Serie
    datos_serial_sinteticos = """t_us,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,p_raw,t_raw
44861950,712,142,-15858,-46,67,13,479888,534000
44963950,725,91,-15907,-18,85,29,479904,534016
"""
    
    # Guardar archivo temporal para prueba
    archivo_temp = "prueba_serial_temp.csv"
    with open(archivo_temp, "w") as f:
        f.write(datos_serial_sinteticos)
        
    # Probar función de carga CSV
    df_csv = cargar_csv_serial(archivo_temp)
    df_convertido = convertir_a_unidades_fisicas(df_csv)
    
    print("\n[OK] Datos cargados correctamente desde el CSV de prueba (Aceleración en m/s²):")
    print(df_convertido[['t_s', 'ax', 'ay', 'az', 'gx', 'gy', 'gz']])
    
    # Limpiar archivo temporal de prueba
    if os.path.exists(archivo_temp):
        os.remove(archivo_temp)

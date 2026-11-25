import struct
import numpy as np
import pandas as pd

# Gravedad local en Quito (~2850 m s.n.m.)
G_QUITO = 9.772

# Factores de escala configurados en adquisicion_esp32.ino:
# MPU_ACCEL = +-2g  -> 16384.0 LSB/g
# MPU_GYRO  = +-250 dps -> 131.0 LSB/(deg/s)
LSB_A = 16384.0 / G_QUITO
LSB_G = 131.0 * (180.0 / np.pi)


def parse_calib(calib_path):
    """Lee /calib_NNN.txt y extrae metadatos y coeficientes BMP280 (0x88..0x9F)."""
    meta = {}
    calib_bytes = bytearray()
    reading_table = False

    with open(calib_path, 'r', encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s or s in ('CONFIGURACION_REGISTRO', 'CALIBRACION_FABRICA_BMP280'):
                continue
            if s == 'registro,byte_hex':
                reading_table = True
                continue
            if reading_table:
                _, hex_val = s.split(',')
                calib_bytes.append(int(hex_val, 16))
            elif '=' in s:
                k, v = s.split('=', 1)
                meta[k] = v

    if len(calib_bytes) != 24:
        raise ValueError(f"Se esperaban 24 bytes de calibracion BMP280, se leyeron {len(calib_bytes)}")

    vals = struct.unpack('<HhhHhhhhhhhh', bytes(calib_bytes))
    keys = ['T1', 'T2', 'T3', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9']
    meta['calib'] = dict(zip(keys, vals))
    return meta


def compensate_bmp280(adc_T, adc_P, c):
    """Compensacion en coma flotante segun hoja de datos de Bosch BMP280."""
    v1 = (adc_T / 16384.0 - c['T1'] / 1024.0) * c['T2']
    v2 = ((adc_T / 131072.0 - c['T1'] / 8192.0) ** 2) * c['T3']
    tf = v1 + v2
    T = tf / 5120.0

    v1 = tf / 2.0 - 64000.0
    v2 = v1 * v1 * c['P6'] / 32768.0
    v2 = v2 + v1 * c['P5'] * 2.0
    v2 = v2 / 4.0 + c['P4'] * 65536.0
    v1 = (c['P3'] * v1 * v1 / 524288.0 + c['P2'] * v1) / 524288.0
    v1 = (1.0 + v1 / 32768.0) * c['P1']

    # Evitar division por cero si hay alguna lectura corrupta
    v1 = np.where(v1 == 0, np.nan, v1)
    p = (1048576.0 - adc_P - v2 / 4096.0) * 6250.0 / v1
    v1 = c['P9'] * p * p / 2147483648.0
    v2 = p * c['P8'] / 32768.0
    P = p + (v1 + v2 + c['P7']) / 16.0
    return T, P


def load_session(run_id, folder="."):
    """
    Carga datos_NNN.csv y calib_NNN.txt generados por adquisicion_esp32.ino.
    Parametros:
        run_id : int o str (ej. 1, '001', o 'datos_001')
        folder : carpeta donde estan los archivos
    """
    if isinstance(run_id, int):
        num_str = f"{run_id:03d}"
    else:
        num_str = str(run_id).replace("datos_", "").replace("calib_", "").replace(".csv", "").replace(".txt", "")
        if num_str.isdigit():
            num_str = f"{int(num_str):03d}"

    csv_path = f"{folder}/datos_{num_str}.csv"
    calib_path = f"{folder}/calib_{num_str}.txt"

    meta = parse_calib(calib_path)
    raw = pd.read_csv(csv_path)

    # Tiempo en segundos relativo al inicio del registro (esp_timer_get_time es int64 en us)
    t_us = raw['t_us'].to_numpy(dtype=np.int64)
    t = (t_us - t_us[0]) * 1e-6
    dt = np.diff(t)

    # Conversion de cuentas ADC crudas a unidades SI (m/s^2 y rad/s)
    ax = raw['ax_raw'].to_numpy(dtype=np.float64) / LSB_A
    ay = raw['ay_raw'].to_numpy(dtype=np.float64) / LSB_A
    az = raw['az_raw'].to_numpy(dtype=np.float64) / LSB_A

    gx = raw['gx_raw'].to_numpy(dtype=np.float64) / LSB_G
    gy = raw['gy_raw'].to_numpy(dtype=np.float64) / LSB_G
    gz = raw['gz_raw'].to_numpy(dtype=np.float64) / LSB_G

    # Compensacion de presion (Pa) y temperatura (°C) del BMP280
    T_bmp, P_pa = compensate_bmp280(
        raw['t_raw'].to_numpy(dtype=np.float64),
        raw['p_raw'].to_numpy(dtype=np.float64),
        meta['calib']
    )

    # Tiempos exactos de eventos del pulsador (en segundos relativos al inicio)
    ev_mask = raw['evento'].to_numpy() == 1
    ev_t_us = raw['evento_t_us'].to_numpy(dtype=np.int64)
    evento_t_rel = np.where(ev_mask & (ev_t_us > 0), (ev_t_us - t_us[0]) * 1e-6, np.nan)

    df = pd.DataFrame({
        'seq': raw['seq'],
        't': t,
        'ax': ax, 'ay': ay, 'az': az,
        'gx': gx, 'gy': gy, 'gz': gz,
        'P_pa': P_pa,
        'T_bmp': T_bmp,
        'evento': ev_mask,
        'evento_t': evento_t_rel,
        'saltos_tiempo': raw['saltos_tiempo'],
        'fallos_i2c': raw['fallos_i2c']
    })

    info = {
        'run_id': num_str,
        'samples': len(df),
        'duration_s': float(t[-1]) if len(t) > 1 else 0.0,
        'fs_real_hz': float((len(t) - 1) / (t[-1] - t[0])) if len(t) > 1 and t[-1] > t[0] else 0.0,
        'dt_mean_ms': float(np.mean(dt) * 1e3) if len(dt) > 0 else 0.0,
        'dt_max_ms': float(np.max(dt) * 1e3) if len(dt) > 0 else 0.0,
        'saltos_tiempo_total': int(raw['saltos_tiempo'].iloc[-1]),
        'fallos_i2c_total': int(raw['fallos_i2c'].iloc[-1]),
        'eventos_total': int(ev_mask.sum()),
        'mpu_id': meta.get('MPU_ID', 'N/A'),
        'bmp_id': meta.get('BMP_ID', 'N/A'),
    }
    return df, info


if __name__ == '__main__':
    # Prueba rapida con datos_001.csv y calib_001.txt
    df, info = load_session(1)
    print("=== RESUMEN DE ADQUISICION ===")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print("\nPrimeras 5 filas:")
    print(df.head())
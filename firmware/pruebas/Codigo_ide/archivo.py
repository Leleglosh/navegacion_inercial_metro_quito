import struct
import numpy as np
import pandas as pd
from scipy import signal

G_QUITO = 9.772  # m/s^2 gravedad local Quito
LSB_A = 8192.0 / G_QUITO          # Cuentas por (m/s^2) a +-4g
LSB_G = 65.5 * (180.0 / np.pi)    # Cuentas por (rad/s) a +-500 dps

REC_DTYPE = np.dtype([
    ('t_us', '<u4'),
    ('seq', '<u2'),
    ('flags', 'u1'),
    ('rsv', 'u1'),
    ('a', '<i2', 3),
    ('g', '<i2', 3),
    ('m', '<i2', 3),
    ('t_mpu', '<i2'),
    ('p_raw', '<i4'),
    ('t_raw', '<i4')
])

def parse_hdr(hdr_path):
    meta = {}
    with open(hdr_path, 'r') as f:
        for line in f:
            k, v = line.strip().split('=', 1)
            meta[k] = v
    raw_bytes = bytes.fromhex(meta['BMP_CALIB'])
    # Desempaquetar coeficientes BMP280: T1(H), T2(h), T3(h), P1(H), P2..P9(h)
    vals = struct.unpack('<HhhHhhhhhhhh', raw_bytes)
    keys = ['T1', 'T2', 'T3', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9']
    meta['calib'] = dict(zip(keys, vals))
    return meta

def compensate_bmp280(adc_T, adc_P, c):
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
    p = (1048576.0 - adc_P - v2 / 4096.0) * 6250.0 / v1
    v1 = c['P9'] * p * p / 2147483648.0
    v2 = p * c['P8'] / 32768.0
    P = p + (v1 + v2 + c['P7']) / 16.0
    return T, P

def load_session(prefix):
    """Carga LOGnnnn.BIN y LOGnnnn.HDR y devuelve un DataFrame listo."""
    meta = parse_hdr(f"{prefix}.HDR")
    raw = np.fromfile(f"{prefix}.BIN", dtype=REC_DTYPE)

    # Desenrollar micros() (overflow cada 71.6 min)
    dt_us = np.diff(raw['t_us'].astype(np.int64), prepend=raw['t_us'][0]) % (2**32)
    t = np.cumsum(dt_us) * 1e-6

    # Verificar pérdidas de paquetes
    dseq = (np.diff(raw['seq'].astype(np.int32)) % 65536) - 1
    lost = int(np.clip(dseq, 0, None).sum())
    fs_real = (len(t) - 1) / (t[-1] - t[0])

    # Convertir unidades
    acc = raw['a'].astype(np.float64) / LSB_A
    gyr = raw['g'].astype(np.float64) / LSB_G
    temp_mpu = (raw['t_mpu'].astype(np.float64) / 333.87) + 21.0

    # Compensar barómetro solo en filas con flag b0 == 1
    baro_mask = (raw['flags'] & 0x01) > 0
    P_pa = np.full(len(t), np.nan)
    T_bmp = np.full(len(t), np.nan)
    if np.any(baro_mask):
        tb, pb = compensate_bmp280(
            raw['t_raw'][baro_mask].astype(np.float64),
            raw['p_raw'][baro_mask].astype(np.float64),
            meta['calib']
        )
        T_bmp[baro_mask] = tb
        P_pa[baro_mask] = pb

    df = pd.DataFrame({
        't': t,
        'seq': raw['seq'],
        'ax': acc[:, 0], 'ay': acc[:, 1], 'az': acc[:, 2],
        'gx': gyr[:, 0], 'gy': gyr[:, 1], 'gz': gyr[:, 2],
        'temp_mpu': temp_mpu,
        'P_pa': P_pa,
        'T_bmp': T_bmp,
        'btn_state': (raw['flags'] & 0x04) > 0,
        'btn_edge': (raw['flags'] & 0x08) > 0,
    })

    info = {
        'samples': len(df),
        'duration_min': t[-1] / 60.0,
        'fs_real_hz': fs_real,
        'lost_packets': lost,
        'mpu_id': meta['MPU_WHO_AM_I']
    }
    return df, info
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Aceleracion local provisional para las primeras graficas.
# Sustituir por un valor fisico justificado para Quito antes del informe final.
G_REFERENCIA = 9.81  # m/s^2 (provisional)
SENSIBILIDAD_ACEL = 16384.0  # cuentas/g, rango +/- 2g
SENSIBILIDAD_GIRO = 131.0  # cuentas/(grados/s), rango +/- 250 grados/s


def leer_coeficientes_bmp280(ruta: Path) -> dict[str, int]:
    """Decodifica los 24 bytes 0x88..0x9F guardados por el firmware."""
    texto = ruta.read_text(encoding="utf-8-sig")
    registros = {}
    for linea in texto.splitlines():
        coincidencia = re.fullmatch(r"\s*0x([0-9a-fA-F]{2})\s*,\s*0x([0-9a-fA-F]{2})\s*", linea)
        if coincidencia:
            registros[int(coincidencia.group(1), 16)] = int(coincidencia.group(2), 16)

    faltan = [i for i in range(0x88, 0xA0) if i not in registros]
    if faltan:
        raise ValueError(f"Faltan coeficientes BMP280 en {ruta.name}: {[hex(x) for x in faltan]}")

    def u16(base: int) -> int:
        return int.from_bytes(bytes([registros[base], registros[base + 1]]), "little", signed=False)

    def s16(base: int) -> int:
        return int.from_bytes(bytes([registros[base], registros[base + 1]]), "little", signed=True)

    parametros = {
        "T1": u16(0x88), "T2": s16(0x8A), "T3": s16(0x8C),
        "P1": u16(0x8E), "P2": s16(0x90), "P3": s16(0x92),
        "P4": s16(0x94), "P5": s16(0x96), "P6": s16(0x98),
        "P7": s16(0x9A), "P8": s16(0x9C), "P9": s16(0x9E),
    }
    if parametros["P1"] == 0:
        raise ValueError("Coeficiente dig_P1=0: la calibracion BMP280 no es valida")
    return parametros


def compensar_bmp280(t_raw: np.ndarray, p_raw: np.ndarray, d: dict[str, int]):
    """Compensacion en coma flotante segun Bosch BMP280, apartado 8.1."""
    t = np.asarray(t_raw, dtype=np.float64)
    p_adc = np.asarray(p_raw, dtype=np.float64)
    v1t = (t / 16384.0 - d["T1"] / 1024.0) * d["T2"]
    v2t = ((t / 131072.0 - d["T1"] / 8192.0) ** 2) * d["T3"]
    t_fine = np.trunc(v1t + v2t)
    temp_c = (v1t + v2t) / 5120.0

    v1 = t_fine / 2.0 - 64000.0
    v2 = v1 * v1 * d["P6"] / 32768.0
    v2 = v2 + v1 * d["P5"] * 2.0
    v2 = (v2 / 4.0) + d["P4"] * 65536.0
    v1 = (d["P3"] * v1 * v1 / 524288.0 + d["P2"] * v1) / 524288.0
    v1 = (1.0 + v1 / 32768.0) * d["P1"]
    if np.any(v1 == 0):
        raise ValueError("Error compensando presion BMP280: divisor igual a cero")
    presion_pa = (1048576.0 - p_adc - v2 / 4096.0) * 6250.0 / v1
    v1 = d["P9"] * presion_pa * presion_pa / 2147483648.0
    v2 = presion_pa * d["P8"] / 32768.0
    presion_pa = presion_pa + (v1 + v2 + d["P7"]) / 16.0
    return temp_c, presion_pa


def guardar_grafica(t, series, titulo, ylabel, destino, eventos):
    plt.figure(figsize=(11, 4.5))
    for y, nombre in series:
        plt.plot(t, y, label=nombre, linewidth=1.0)
    for i, instante in enumerate(eventos):
        plt.axvline(instante, linestyle=":", alpha=0.55,
                    label="Pulsador" if i == 0 else None)
    plt.title(titulo)
    plt.xlabel("Tiempo desde la primera muestra (s)")
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(destino, dpi=170)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Graficas fisicas de registros ESP32 + GY-91")
    parser.add_argument("--csv", type=Path, required=True, help="Archivo datos_XXX.csv ORIGINAL")
    parser.add_argument("--calib", type=Path, required=True, help="Pareja calib_XXX.txt del mismo registro")
    args = parser.parse_args()

    csv = args.csv.expanduser().resolve()
    calib = args.calib.expanduser().resolve()
    if not csv.is_file():
        parser.error(f"No existe el CSV: {csv}")
    if not calib.is_file():
        parser.error(f"No existe el archivo de calibracion: {calib}")
    raiz_repo = Path(__file__).resolve().parent.parent
    carpeta_graficas = raiz_repo / "resultados" / "graficas"
    carpeta_procesados = raiz_repo / "datos" / "procesados"
    carpeta_graficas.mkdir(parents=True, exist_ok=True)
    carpeta_procesados.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv)
    columnas = ["seq", "t_us", "ax_raw", "ay_raw", "az_raw", "gx_raw", "gy_raw", "gz_raw", "p_raw", "t_raw", "evento", "evento_t_us"]
    faltantes = [c for c in columnas if c not in df.columns]
    if faltantes:
        raise ValueError(f"Columnas que faltan en CSV: {faltantes}")
    if len(df) < 2:
        raise ValueError("Se necesitan al menos dos muestras")
    if df[columnas].isna().any().any():
        raise ValueError("El CSV tiene datos faltantes en columnas obligatorias")

    t_us = df["t_us"].to_numpy(dtype=np.int64)
    if np.any(np.diff(t_us) <= 0):
        raise ValueError("Las marcas de tiempo no estan estrictamente ordenadas")
    t = (t_us - t_us[0]) / 1e6
    eventos = (df.loc[df["evento"] == 1, "evento_t_us"].to_numpy(dtype=np.int64) - t_us[0]) / 1e6
    eventos = eventos[(eventos >= 0) & (eventos <= t[-1])]

    convertido = pd.DataFrame({"seq":df["seq"], "t_s": t, "t_us":t_us})
    for eje in "xyz":
        convertido[f"a{eje}_m_s2"] = df[f"a{eje}_raw"].to_numpy(dtype=float) * G_REFERENCIA / SENSIBILIDAD_ACEL
        convertido[f"g{eje}_deg_s"] = df[f"g{eje}_raw"].to_numpy(dtype=float) / SENSIBILIDAD_GIRO

    coef = leer_coeficientes_bmp280(calib)
    temp_c, presion_pa = compensar_bmp280(df["t_raw"], df["p_raw"], coef)
    convertido["temperatura_C"] = temp_c
    convertido["presion_Pa"] = presion_pa
    convertido["presion_hPa"] = presion_pa / 100.0
    convertido["evento"] = df["evento"].to_numpy()
    convertido["evento_t_us"] = df["evento_t_us"].to_numpy()

    prefijo = csv.stem
    guardar_grafica(t, [(convertido[f"a{eje}_m_s2"], f"a{eje}") for eje in "xyz"],
                   f"Aceleracion del IMU - {prefijo}", "Aceleracion especifica (m/s²)",
                   carpeta_graficas / f"{prefijo}_aceleracion.png", eventos)
    guardar_grafica(t, [(convertido[f"g{eje}_deg_s"], f"g{eje}") for eje in "xyz"],
                   f"Velocidad angular - {prefijo}", "Velocidad angular (grados/s)",
                   carpeta_graficas / f"{prefijo}_giroscopio.png", eventos)
    guardar_grafica(t, [(convertido["presion_hPa"], "Presion")],
                   f"Presion compensada BMP280 - {prefijo}", "Presion (hPa)",
                   carpeta_graficas / f"{prefijo}_presion.png", eventos)
    guardar_grafica(t, [(convertido["temperatura_C"], "Temperatura")],
                   f"Temperatura compensada BMP280 - {prefijo}", "Temperatura (°C)",
                   carpeta_graficas / f"{prefijo}_temperatura.png", eventos)

    # Evidencia complementaria de irregularidades del reloj de adquisicion.
    dt_ms = np.diff(t) * 1000.0
    plt.figure(figsize=(11, 4.5))
    plt.plot(t[1:], dt_ms, linewidth=0.8, label="Intervalo observado")
    plt.axhline(9.5, linestyle="--", alpha=0.7, label="Periodo objetivo CSV 006: 9.5 ms")
    plt.xlabel("Tiempo desde la primera muestra (s)")
    plt.ylabel("Intervalo entre registros (ms)")
    plt.title(f"Regularidad de adquisicion - {prefijo}")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(carpeta_graficas / f"{prefijo}_intervalos.png", dpi=170)
    plt.close()

    destino = carpeta_procesados / f"{prefijo}_fisico.csv"
    convertido.to_csv(destino, index=False)

    dt = np.diff(t)
    print("=== ANALISIS DEL REGISTRO Y GRAFICAS ===")
    print(f"CSV: {csv.name}")
    print(f"Muestras: {len(df)}")
    print(f"Duracion: {t[-1]:.3f} s")
    print(f"Frecuencia media: {(len(df)-1)/t[-1]:.2f} Hz")
    print(f"Intervalo maximo: {dt.max()*1000:.3f} ms")
    print(f"Eventos: {int((df['evento'] == 1).sum())}")
    print(f"Presion media: {np.mean(presion_pa):.1f} Pa")
    print(f"Temperatura media: {np.mean(temp_c):.2f} °C")
    if not np.all(np.isfinite(presion_pa)) or not np.all((presion_pa > 30000) & (presion_pa < 120000)):
        print("AVISO: presion fuera de rango plausible; comprobar calib_XXX y sensor")
    print(f"CSV procesado: {destino}")
    print(f"Graficas guardadas en: {carpeta_graficas}")
    print("Nota: aceleraciones especificas (incluyen gravedad); aun NO calibradas ni integradas.")


if __name__ == "__main__":
    main()

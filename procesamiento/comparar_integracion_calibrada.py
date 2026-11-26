"""Comparacion del crecimiento del error antes/despues de calibrar — nivel 3.

Ejecutar desde la RAIZ del repositorio:
    python procesamiento/comparar_integracion_calibrada.py

Archivos esperados:
    datos/procesados/datos_009_fisico.csv
    resultados/calibracion/parametros_calibracion.json

Requiere: numpy, pandas, matplotlib y config_fisica.py en procesamiento/.

ATENCION: calcula DESPLAZAMIENTO FICTICIO ESCALAR en reposo. NO es
reconstruccion de trayectoria real ni compensacion de orientacion tridimensional.
Los datos del experimento 009 deben haber sido convertidos con g_estandar=9.80665.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config_fisica import GRAVEDAD_QUITO_MS2

COLS = ["ax_m_s2", "ay_m_s2", "az_m_s2"]
EJES = "XYZ"


def integrar_taylor(t: np.ndarray, a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Taylor: 1.er grado para velocidad, 2.o para posicion.

    En cada intervalo se supone aceleracion constante a[i].
    Se parte de v(0)=0 y x(0)=0.
    """
    n = len(t)
    v = np.zeros(n, dtype=float)
    x = np.zeros(n, dtype=float)
    for i in range(n - 1):
        dt = t[i + 1] - t[i]
        v[i + 1] = v[i] + a[i] * dt
        x[i + 1] = x[i] + v[i] * dt + 0.5 * a[i] * dt**2
    return v, x


def integrar_interpolacion(t: np.ndarray, a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Integra exactamente el polinomio LINEAL entre muestras.

    Suponemos a(t) lineal en cada intervalo; por eso:
      delta v = (a_i + a_{i+1})*dt/2
      delta x = v_i*dt + (2*a_i + a_{i+1})*dt**2/6
    Con v(0)=0 y x(0)=0.
    """
    n = len(t)
    v = np.zeros(n, dtype=float)
    x = np.zeros(n, dtype=float)
    for i in range(n - 1):
        dt = t[i + 1] - t[i]
        v[i + 1] = v[i] + 0.5 * (a[i] + a[i + 1]) * dt
        x[i + 1] = x[i] + v[i] * dt + (2 * a[i] + a[i + 1]) * dt**2 / 6
    return v, x


def grafica(t_min: np.ndarray, series: list[tuple[str, np.ndarray]], ylabel: str,
            titulo: str, destino: Path) -> None:
    paso = max(1, len(t_min) // 10000)
    ix = np.arange(0, len(t_min), paso, dtype=int)
    if ix[-1] != len(t_min) - 1:
        ix = np.append(ix, len(t_min) - 1)
    fig, ax = plt.subplots(figsize=(11, 5))
    for etiqueta, y in series:
        ax.plot(t_min[ix], y[ix], label=etiqueta, linewidth=1)
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_xlabel("Tiempo del experimento (min)")
    ax.set_ylabel(ylabel)
    ax.set_title(titulo)
    ax.grid(alpha=.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(destino, dpi=160)
    plt.close(fig)


def analizar(csv: Path, params: Path, salida: Path) -> dict:
    if not csv.is_file():
        raise FileNotFoundError(f"Falta el registro procesado del reposo: {csv}")
    if not params.is_file():
        raise FileNotFoundError(
            f"Faltan parametros de calibracion: {params}\n"
            "Ejecuta primero: python procesamiento/calibrar_seis_caras.py")

    with params.open("r", encoding="utf-8") as f:
        p = json.load(f)

    g = float(GRAVEDAD_QUITO_MS2)
    g_calib = float(p.get("gravedad_referencia_m_s2", np.nan))
    if not np.isclose(g, g_calib, rtol=0, atol=1e-5):
        raise ValueError(
            f"Los parametros del JSON fueron calculados con g={g_calib}, "
            f"pero config_fisica.py indica g={g}. Vuelve a calibrar usando Quito.")

    b = np.array([float(p["sesgo_m_s2"][i]) for i in EJES], dtype=float)
    s = np.array([float(p["escala_adimensional"][i]) for i in EJES], dtype=float)
    if not (np.all(np.isfinite(b)) and np.all(np.isfinite(s)) and np.all(s > 0)):
        raise ValueError("Sesgos o escalas invalidos en los parametros de calibracion")

    columnas_requeridas = ["t_s", *COLS]
    df = pd.read_csv(csv)
    faltan = [c for c in columnas_requeridas if c not in df.columns]
    if faltan:
        raise ValueError(f"El CSV no tiene las columnas: {faltan}")
    if len(df) < 2:
        raise ValueError("Se requieren al menos dos muestras")
    datos = df[columnas_requeridas].to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(datos)):
        raise ValueError("El CSV contiene NaN o valores infinitos")

    t = datos[:, 0] - datos[0, 0]
    dt = np.diff(t)
    if not np.all(dt > 0):
        raise ValueError("Las marcas de tiempo no son estrictamente crecientes")
    a_original = datos[:, 1:4]
    a_calibrada = (a_original - b) / s

    # MISMA direccion para comparar ANTES y DESPUES: proyeccion sobre el
    # vector promedio calibrado del reposo. Asumimos orientacion fija.
    media_calibrada = a_calibrada.mean(axis=0)
    norma_media_cal = np.linalg.norm(media_calibrada)
    if norma_media_cal < 1:
        raise ValueError("Norma media demasiado pequena; revisa datos o unidades")
    vertical_aproximada = media_calibrada / norma_media_cal

    # La proyeccion usa la MISMA direccion en ambas series; sin ajuste de
    # medias por separado, para no ocultar el sesgo que buscamos evaluar.
    residuo_antes = a_original @ vertical_aproximada - g
    residuo_despues = a_calibrada @ vertical_aproximada - g

    metodos = {
        "taylor": integrar_taylor,
        "interpolacion": integrar_interpolacion,
    }
    resultados = {}
    for metodo, funcion in metodos.items():
        v_antes, x_antes = funcion(t, residuo_antes)
        v_despues, x_despues = funcion(t, residuo_despues)
        reduccion_x = float("nan")
        if abs(x_antes[-1]) > 1e-12:
            reduccion_x = 100 * (1 - abs(x_despues[-1]) / abs(x_antes[-1]))
        resultados[metodo] = {
            "v_antes": v_antes, "x_antes": x_antes,
            "v_despues": v_despues, "x_despues": x_despues,
            "reduccion_absoluta_porcentaje": reduccion_x,
        }

    salida.mkdir(parents=True, exist_ok=True)
    t_min = t / 60.0
    grafica(t_min,
            [("Sin calibrar", residuo_antes), ("Calibrado", residuo_despues)],
            "Aceleracion residual proyectada (m/s²)",
            f"{csv.stem}: aceleracion residual antes y despues de calibrar",
            salida / "01_residual_antes_despues.png")
    for metodo, r in resultados.items():
        grafica(t_min,
                [("Sin calibrar", r["x_antes"]), ("Calibrado", r["x_despues"])],
                "Desplazamiento ficticio acumulado (m)",
                f"{csv.stem}: doble integracion - {metodo}",
                salida / f"02_integracion_{metodo}.png")

    # Muestra ligera de la serie integrada ~ 1 fila/s. El algoritmo SI
    # integra el CSV completo: esta exportacion es solo para graficar/auditar.
    frecuencia = (len(t) - 1) / t[-1]
    paso = max(1, round(frecuencia))
    idx = np.arange(0, len(t), paso, dtype=int)
    if idx[-1] != len(t)-1:
        idx = np.append(idx, len(t)-1)
    tabla = {
        "t_s": t[idx],
        "acel_residual_original_m_s2": residuo_antes[idx],
        "acel_residual_calibrada_m_s2": residuo_despues[idx],
    }
    for metodo, r in resultados.items():
        for nombre in ("v_antes", "v_despues", "x_antes", "x_despues"):
            tabla[f"{metodo}_{nombre}_m{'_s' if nombre[0]=='v' else ''}"] = r[nombre][idx]
    pd.DataFrame(tabla).to_csv(salida / "comparacion_integracion_muestreada.csv", index=False)

    media_original = a_original.mean(axis=0)
    norma_original = float(np.linalg.norm(media_original))
    norma_calibrada = float(np.linalg.norm(media_calibrada))
    err_ori = norma_original - g
    err_cal = norma_calibrada - g
    reduccion_norma = 100 * (1 - abs(err_cal) / abs(err_ori)) if err_ori else float("nan")
    duracion = float(t[-1])

    resumen = {
        "archivo_reposo": csv.name,
        "archivo_calibracion": params.name,
        "gravedad_local_m_s2": g,
        "muestras": int(len(t)),
        "duracion_s": duracion,
        "frecuencia_media_hz": float(frecuencia),
        "intervalo_maximo_ms": float(dt.max() * 1000),
        "intervalos_mayores_15ms": int((dt > .015).sum()),
        "direccion_vertical_estimada_3d": [float(v) for v in vertical_aproximada],
        "norma_media_antes_m_s2": norma_original,
        "norma_media_despues_m_s2": norma_calibrada,
        "diferencia_norma_antes_m_s2": float(err_ori),
        "diferencia_norma_despues_m_s2": float(err_cal),
        "reduccion_diferencia_norma_pct": float(reduccion_norma),
        "residuo_antes_media_m_s2": float(residuo_antes.mean()),
        "residuo_despues_media_m_s2": float(residuo_despues.mean()),
        "residuo_antes_std_m_s2": float(residuo_antes.std(ddof=1)),
        "residuo_despues_std_m_s2": float(residuo_despues.std(ddof=1)),
        "descripcion_metodos": {
            "taylor": "Taylor grado 1 para velocidad y grado 2 para posicion; aceleracion constante por intervalo",
            "interpolacion": "integracion exacta de la interpolacion lineal de la aceleracion en cada intervalo",
        },
        "metodos": {
            m: {
                "velocidad_final_antes_m_s": float(r["v_antes"][-1]),
                "velocidad_final_despues_m_s": float(r["v_despues"][-1]),
                "desplazamiento_final_antes_m": float(r["x_antes"][-1]),
                "desplazamiento_final_despues_m": float(r["x_despues"][-1]),
                "reduccion_desplazamiento_absoluto_pct": float(r["reduccion_absoluta_porcentaje"]),
            } for m, r in resultados.items()
        },
        "interpretacion": (
            "Desplazamiento ficticio escalar por doble integracion del residual "
            "de aceleracion en direccion de gravedad estimada. No constituye "
            "la trayectoria 3D ni garantiza precision de navegacion. "
            "Ambas series usan una misma direccion proyectada y los tiempos reales. "
        "Metodos: Taylor e interpolacion lineal por intervalos."
        ),
    }

    (salida / "resumen_integracion.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    lineas = [
        f"=== NIVEL 3: {csv.stem}, ANTES Y DESPUES DE CALIBRAR ===",
        f"CSV: {csv.name} | Parametros: {params.name}",
        f"Muestras: {len(t)}; duracion: {duracion:.3f} s; frecuencia media: {frecuencia:.3f} Hz",
        f"Intervalo maximo: {dt.max()*1000:.3f} ms; dt >15ms: {(dt>.015).sum()}",
        f"Gravedad local Quito: {g:.4f} m/s2",
        f"Vector vertical aproximado (X,Y,Z): {vertical_aproximada.round(6).tolist()}",
        f"Norma media ANTES: {norma_original:.6f} m/s2 (diferencia {err_ori:+.6f})",
        f"Norma media DESPUES: {norma_calibrada:.6f} m/s2 (diferencia {err_cal:+.6f})",
        f"Reduccion |diferencia de norma|: {reduccion_norma:.2f}%",
        f"Residual proyectado ANTES: media {residuo_antes.mean():+.6f}, desv {residuo_antes.std(ddof=1):.6f} m/s2",
        f"Residual proyectado DESPUES: media {residuo_despues.mean():+.6f}, desv {residuo_despues.std(ddof=1):.6f} m/s2",
        "",
    ]
    for m, r in resultados.items():
        lineas += [
            f"METODO: {m} ({'Taylor grados 1 y 2' if m == 'taylor' else 'interpolacion lineal de aceleracion'})",
            f"  SIN calibrar: v_final={r['v_antes'][-1]:+.4f} m/s; x_final={r['x_antes'][-1]:+.2f} m",
            f"  CALIBRADO:    v_final={r['v_despues'][-1]:+.4f} m/s; x_final={r['x_despues'][-1]:+.2f} m",
            f"  Reduccion de |desplazamiento ficticio final|: {r['reduccion_absoluta_porcentaje']:.2f}%",
            "",
        ]
    if not 3590 < duracion < 3620:
        lineas.append("AVISO: la duracion no corresponde aproximadamente a 1 hora")
    if dt.max() > 0.1:
        lineas.append("AVISO: pausas de adquisicion >100 ms; incluidas mediante dt real")
    lineas += [
        "NOTA METODOLOGICA: no es posicion real, ni integra rotaciones/giroscopio.",
        "La referencia vertical se aproxima con el promedio calibrado del propio reposo.",
        "Las dos series usan la MISMA direccion; no se centra la media por separado.",
        "Taylor supone aceleracion constante dentro de cada intervalo; interpolacion supone variacion lineal.",
        "La calibracion se obtuvo de los CSV 010-015, no del reposo 009.",
        "En reposo, la referencia fisica del desplazamiento es 0 m.",
    ]
    texto = "\n".join(lineas) + "\n"
    (salida / "resumen_integracion.txt").write_text(texto, encoding="utf-8")
    print("\n"+texto)
    print(f"Resultados guardados en: {salida.resolve()}")
    return resumen


def main() -> None:
    raiz = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Comparacion final de nivel 3: reposo, calibracion e integracion")
    parser.add_argument("--csv", type=Path,
                        default=raiz / "datos" / "procesados" / "datos_009_fisico.csv",
                        help="Registro de reposo en unidades fisicas, convertido con g estandar=9.80665")
    parser.add_argument("--parametros", type=Path,
                        default=raiz / "resultados" / "calibracion" / "parametros_calibracion.json",
                        help="Parametros de seis caras con gravedad de Quito=9.7726")
    parser.add_argument("--salida", type=Path,
                        default=raiz / "resultados" / "nivel3",
                        help="Carpeta de graficas y resumen")
    a = parser.parse_args()
    try:
        analizar(a.csv.resolve(), a.parametros.resolve(), a.salida.resolve())
    except (ValueError, FileNotFoundError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

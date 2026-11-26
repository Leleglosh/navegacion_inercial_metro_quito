"""Analisis preliminar del experimento de reposo para Navegacion Inercial.

Uso (desde la raiz del repositorio):
  python procesamiento/analizar_reposo.py \
    --csv datos/procesados/datos_008_fisico.csv

El CSV debe ser el producido por graficar_nivel2.py. No modifica datos crudos.
Las integraciones de 'error equivalente 1D' NO son una trayectoria inercial
ni sustituyen la calibracion de seis caras o la compensacion de orientacion.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from config_fisica import GRAVEDAD_QUITO_MS2

ACEL = ['ax_m_s2', 'ay_m_s2', 'az_m_s2']
GIRO = ['gx_deg_s', 'gy_deg_s', 'gz_deg_s']


def integrar(t: np.ndarray, a: np.ndarray, metodo: str):
    dt = np.diff(t)
    v = np.zeros(len(t), dtype=float)
    x = np.zeros(len(t), dtype=float)
    if metodo == 'rectangulo':
        dv = a[:-1] * dt
    else:
        dv = 0.5 * (a[:-1] + a[1:]) * dt
    v[1:] = np.cumsum(dv)
    if metodo == 'rectangulo':
        dx = v[:-1] * dt
    else:
        dx = 0.5 * (v[:-1] + v[1:]) * dt
    x[1:] = np.cumsum(dx)
    return v, x


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', type=Path, required=True, help='CSV fisico del experimento de reposo')
    p.add_argument('--g', type=float, default=GRAVEDAD_QUITO_MS2, help='Gravedad local de referencia en m/s² (defecto: Quito 9.7726)')
    p.add_argument('--salida', type=Path, default=None, help='Carpeta para resumen y figuras')
    args = p.parse_args()
    if not args.csv.is_file():
        p.error(f'No existe el archivo: {args.csv}')
    if args.g <= 0:
        p.error('--g debe ser positivo')
    df = pd.read_csv(args.csv)
    necesarias = ['t_s', *ACEL, *GIRO, 'presion_Pa', 'temperatura_C']
    faltan = [x for x in necesarias if x not in df.columns]
    if faltan:
        p.error(f'Faltan columnas: {faltan}')
    if len(df) < 2:
        p.error('Hay menos de dos muestras')
    if df[necesarias].isna().any().any():
        p.error('El CSV tiene celdas vacias')

    t = df['t_s'].to_numpy(dtype=np.float64)
    t = t - t[0]
    dt = np.diff(t)
    if not np.isfinite(dt).all() or np.any(dt <= 0):
        p.error('Las marcas de tiempo no son estrictamente crecientes')
    a = df[ACEL].to_numpy(dtype=float)
    w = df[GIRO].to_numpy(dtype=float)
    magnitud = np.linalg.norm(a, axis=1)
    promedio_a = np.mean(a, axis=0)
    std_a = np.std(a, axis=0, ddof=1)
    promedio_w = np.mean(w, axis=0)
    std_w = np.std(w, axis=0, ddof=1)
    norm_promedio = np.linalg.norm(promedio_a)
    dif_g = norm_promedio - args.g
    duracion = t[-1]
    frecuencia = (len(t)-1)/duracion
    presion = df['presion_Pa'].to_numpy(dtype=float)
    temperatura = df['temperatura_C'].to_numpy(dtype=float)

    # Escenario *ilustrativo*: proyeccion sobre la direccion media observada,
    # suponiendo que dicha direccion es la vertical del sensor durante el reposo.
    # No identifica sesgos 3D ni resuelve orientacion: se necesitan seis caras.
    u = promedio_a/norm_promedio
    a_paralela = a @ u
    residuo = a_paralela - args.g
    residuo_sin_media = a_paralela - np.mean(a_paralela)
    integrales = {}
    for metodo in ('rectangulo', 'trapecio'):
        v0, x0 = integrar(t, residuo, metodo)
        v1, x1 = integrar(t, residuo_sin_media, metodo)
        integrales[metodo] = (v0,x0,v1,x1)

    salida = args.salida or (Path(__file__).resolve().parent.parent/'resultados'/'reposo')
    salida.mkdir(parents=True, exist_ok=True)
    prefijo = args.csv.stem.replace('_fisico','')
    contenido = [
        f'REPOSO - {prefijo} (ANALISIS PRELIMINAR)',
        f'Muestras: {len(df)}',
        f'Duracion observada: {duracion:.3f} s ({duracion/60:.2f} min)',
        f'Frecuencia media observada: {frecuencia:.3f} Hz',
        f'Intervalo medio: {dt.mean()*1e3:.3f} ms',
        f'Intervalo maximo: {dt.max()*1e3:.3f} ms',
        f'Intervalos > 15 ms: {int(np.sum(dt>0.015))}',
        f'Gravedad local de referencia utilizada: {args.g:.5f} m/s²',
        '',
        'ACELERACION ESPECIFICA (m/s²; incluye gravedad):',
    ]
    for i,eje in enumerate('XYZ'):
        contenido.append(f'  {eje}: media={promedio_a[i]:.6f}; desviacion={std_a[i]:.6f}')
    contenido += [
        f'Norma del vector de medias: {norm_promedio:.6f} m/s²',
        f'Diferencia norma - g_ref: {dif_g:+.6f} m/s²',
        'Esta diferencia NO es el sesgo 3D de cada eje: usar calibracion de seis caras.',
        '',
        'GIROSCOPIO (°/s; la media es sesgo estimado SI se mantuvo inmovil):',
    ]
    for i,eje in enumerate('XYZ'):
        contenido.append(f'  {eje}: media={promedio_w[i]:+.6f}; desviacion={std_w[i]:.6f}; deriva simple={promedio_w[i]*3600:+.1f} °/h')
    contenido += [
        '',
        f'Presion: media={presion.mean():.2f} Pa; desviacion={presion.std(ddof=1):.2f} Pa',
        f'Temperatura: media={temperatura.mean():.3f} °C; desviacion={temperatura.std(ddof=1):.4f} °C',
        '',
        'INTEGRACION ILUSTRATIVA DEL ERROR ESCALAR EN DIRECCION DE GRAVEDAD',
        'Se integra a_paralela - g_ref, NO aceleracion lineal 3D real.',
        'La serie centrada resta el promedio calculado con el mismo experimento:',
        'solo permite observar la contribucion residual, NO es calibracion independiente.',
    ]
    for metodo in ('rectangulo','trapecio'):
        v0,x0,v1,x1 = integrales[metodo]
        contenido.append(f'  {metodo}: sin corregir media -> v_fin={v0[-1]:+.4f} m/s; x_fin={x0[-1]:+.2f} m')
        contenido.append(f'  {metodo}: media centrada -> v_fin={v1[-1]:+.4f} m/s; x_fin={x1[-1]:+.2f} m')
    if not 3590 <= duracion <= 3620:
        contenido.append('ATENCION: la duracion NO corresponde a una hora completa; verificar registro.')
    if df.get('evento', pd.Series(np.zeros(len(df)))).sum() > 0:
        contenido.append('ATENCION: hay eventos de boton; comprobar si el montaje fue tocado.')
    contenido.append('Las pausas de adquisicion pueden afectar las integraciones; se usan tiempos reales.')
    resumen = '\n'.join(contenido)+'\n'
    print(resumen)
    (salida/f'{prefijo}_resumen_reposo.txt').write_text(resumen, encoding='utf-8')

    stride = max(1, len(t)//12000)
    ix = slice(None,None,stride)
    fig, ax = plt.subplots(figsize=(11,4.5))
    for i, eje in enumerate('XYZ'):
        ax.plot(t[ix]/60, a[ix,i], lw=.7, label=f'a{eje} (media {promedio_a[i]:.3f})')
    ax.set(xlabel='Tiempo (min)', ylabel='Aceleracion especifica (m/s²)', title='Reposo: aceleracion en los tres ejes')
    ax.grid(alpha=.3); ax.legend(); fig.tight_layout()
    fig.savefig(salida/f'{prefijo}_aceleracion_reposo.png',dpi=150); plt.close(fig)

    fig,ax=plt.subplots(figsize=(11,4.5))
    for i,eje in enumerate('XYZ'):
        ax.plot(t[ix]/60,w[ix,i],lw=.7,label=f'g{eje} (sesgo {promedio_w[i]:+.3f} °/s)')
    ax.set(xlabel='Tiempo (min)',ylabel='Velocidad angular (°/s)',title='Reposo: velocidad angular')
    ax.grid(alpha=.3); ax.legend(); fig.tight_layout()
    fig.savefig(salida/f'{prefijo}_giroscopio_reposo.png',dpi=150); plt.close(fig)

    fig,ax=plt.subplots(figsize=(11,4.5))
    ax.plot(t[ix]/60, magnitud[ix],label='||a|| observado',lw=.7)
    ax.axhline(args.g,color='black',ls='--',label='g local de Quito')
    ax.set(xlabel='Tiempo (min)',ylabel='Magnitud de aceleracion (m/s²)',title='Reposo: magnitud y referencia de gravedad')
    ax.grid(alpha=.3); ax.legend(); fig.tight_layout()
    fig.savefig(salida/f'{prefijo}_magnitud_reposo.png',dpi=150); plt.close(fig)

    fig,ax=plt.subplots(figsize=(11,4.5))
    for metodo,(_,x0,_,x1) in integrales.items():
        ax.plot(t[ix]/60, x0[ix], label=f'{metodo}: residual sin centrar',lw=1)
        ax.plot(t[ix]/60, x1[ix], label=f'{metodo}: residual centrado',lw=1,ls='--')
    ax.set(xlabel='Tiempo (min)',ylabel='Desplazamiento espurio estimado (m)',title='Experimento en reposo: integracion escalar ilustrativa')
    ax.grid(alpha=.3); ax.legend(); fig.tight_layout()
    fig.savefig(salida/f'{prefijo}_error_integrado_ilustrativo.png',dpi=150); plt.close(fig)

if __name__ == '__main__':
    main()

"""Calibracion acelerometro seis caras (modelo por eje: sesgo + escala).

Ejecutar desde la raiz del repositorio:
    python procesamiento/calibrar_seis_caras.py
    python procesamiento/calibrar_seis_caras.py --gravedad 9.7726

Archivos esperados en datos/procesados/:
    datos_010_fisico.csv -Z, datos_011_fisico.csv +Z,
    datos_012_fisico.csv -X, datos_013_fisico.csv +X,
    datos_014_fisico.csv -Y, datos_015_fisico.csv +Y.

Opcional: datos_009_fisico.csv, para validacion con registro de reposo
independiente (sin usarlo para ajustar los parametros).

Salida: resultados/calibracion/ con CSV, JSON y graficas PNG.
Requiere: pandas, numpy, matplotlib.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from config_fisica import GRAVEDAD_QUITO_MS2

MAPA = {
    '-Z': 'datos_010_fisico.csv',
    '+Z': 'datos_011_fisico.csv',
    '-X': 'datos_012_fisico.csv',
    '+X': 'datos_013_fisico.csv',
    '-Y': 'datos_014_fisico.csv',
    '+Y': 'datos_015_fisico.csv',
}
COLS = ['ax_m_s2', 'ay_m_s2', 'az_m_s2']
EJES = 'XYZ'

def procesar(directorio: Path, salida: Path, reposo: Path, g: float):
    if g <= 0:
        raise ValueError('La gravedad de referencia debe ser positiva.')
    salida.mkdir(parents=True, exist_ok=True)
    lecturas = {}
    resumen = []
    for orientacion, archivo in MAPA.items():
        ruta = directorio / archivo
        if not ruta.is_file():
            raise FileNotFoundError(f'Falta {ruta}. Copia los seis CSV fisicos a la carpeta indicada.')
        df = pd.read_csv(ruta)
        requeridas = COLS + ['t_s']
        faltantes = [c for c in requeridas if c not in df.columns]
        if faltantes:
            raise ValueError(f'{archivo}: faltan columnas {faltantes}')
        if df.empty or not np.all(np.isfinite(df[requeridas].to_numpy(dtype=float))):
            raise ValueError(f'{archivo}: datos vacios o no finitos')
        if not np.all(np.diff(df['t_s'].to_numpy(dtype=float)) > 0):
            raise ValueError(f'{archivo}: las marcas t_s no son estrictamente crecientes')
        lecturas[orientacion] = df
        a = df[COLS].to_numpy(dtype=float)
        med = a.mean(axis=0)
        desv = a.std(axis=0, ddof=1)
        dt = np.diff(df['t_s'].to_numpy(dtype=float))
        resumen.append({
            'orientacion': orientacion,
            'archivo': archivo,
            'muestras': len(df),
            'duracion_s': float(df['t_s'].iloc[-1] - df['t_s'].iloc[0]),
            'frecuencia_media_hz': float((len(df) - 1) / (df['t_s'].iloc[-1] - df['t_s'].iloc[0])),
            'intervalo_maximo_ms': float(dt.max()*1000),
            'intervalos_mayores_15ms': int((dt > .015).sum()),
            'ax_media': float(med[0]), 'ay_media': float(med[1]), 'az_media': float(med[2]),
            'ax_desv': float(desv[0]), 'ay_desv': float(desv[1]), 'az_desv': float(desv[2]),
            'norma_vector_medio_antes': float(np.linalg.norm(med)),
        })

    filas = {r['orientacion']: r for r in resumen}
    bias = np.zeros(3)
    scale = np.zeros(3)
    print('\n=== CALIBRACION DE SEIS CARAS ===')
    print(f'Gravedad local de referencia (Quito): {g:.5f} m/s2')
    for i, eje in enumerate(EJES):
        clave = ['ax_media','ay_media','az_media'][i]
        pos = filas['+'+eje][clave]
        neg = filas['-'+eje][clave]
        bias[i] = (pos + neg)/2
        scale[i] = (pos - neg)/(2*g)
        if not (0.8 < scale[i] < 1.2):
            raise ValueError(f'Escala {eje}={scale[i]:.4f} inesperada. Revisa la orientacion.')
        print(f'{eje}: +g={pos:+.6f}, -g={neg:+.6f}, sesgo={bias[i]:+.6f} m/s2, '
              f'escala={scale[i]:.8f}, correccion: (a-{bias[i]:+.6f})/{scale[i]:.8f}')

    for fila in resumen:
        med = np.array([fila['ax_media'],fila['ay_media'],fila['az_media']])
        calibrado = (med - bias)/scale
        fila['ax_media_calibrada'] = float(calibrado[0])
        fila['ay_media_calibrada'] = float(calibrado[1])
        fila['az_media_calibrada'] = float(calibrado[2])
        fila['norma_vector_medio_despues'] = float(np.linalg.norm(calibrado))
        fila['error_norma_antes'] = float(np.linalg.norm(med)-g)
        fila['error_norma_despues'] = float(np.linalg.norm(calibrado)-g)
        eje = fila['orientacion'][1]
        signo = 1 if fila['orientacion'][0] == '+' else -1
        fila['aceleracion_principal_esperada'] = signo*g
        fila['aceleracion_principal_calibrada'] = float(calibrado[EJES.index(eje)])

    cuadro = pd.DataFrame(resumen)
    cuadro.to_csv(salida / 'resumen_seis_caras.csv', index=False)
    parametros = {
        'modelo':'aceleracion_calibrada_i=(aceleracion_nominal_i-sesgo_i)/escala_i',
        'gravedad_referencia_m_s2':g,
        'unidades_sesgo':'m/s2',
        'orden_ejes':['X','Y','Z'],
        'sesgo_m_s2': {e:float(bias[i]) for i,e in enumerate(EJES)},
        'escala_adimensional': {e:float(scale[i]) for i,e in enumerate(EJES)},
        'mapeo_archivos': MAPA,
        'limitaciones': [
            'Gravedad local de referencia del proyecto: Quito (9.7726 m/s2)',
            'Modelo diagonal: no corrige desalineacion, no ortogonalidad ni acoplamiento cruzado',
            'Posibles inclinaciones de las seis orientaciones',
            'No corrige orientacion, gravedad 3D ni sesgo del giroscopio',
        ],
    }

    orden = ['-X','+X','-Y','+Y','-Z','+Z']
    dic = {r['orientacion']: r for r in resumen}
    antes = [dic[k]['norma_vector_medio_antes'] for k in orden]
    despues = [dic[k]['norma_vector_medio_despues'] for k in orden]
    x = np.arange(6)
    fig, ax = plt.subplots(figsize=(10,5))
    ax.bar(x-.18, antes, .36, label='Antes de calibrar')
    ax.bar(x+.18, despues, .36, label='Despues de calibrar')
    ax.axhline(g, ls='--', color='black', label=f'Referencia g={g:.3f} m/s2')
    ax.set_xticks(x, orden)
    ax.set_ylabel('Norma del vector de aceleracion media (m/s2)')
    ax.set_title('Calibracion de seis caras: magnitud por orientacion')
    ax.set_ylim(min(min(antes), min(despues), g)-.13, max(max(antes), max(despues), g)+.13)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.1), ncol=3)
    ax.grid(axis='y', alpha=.2)
    fig.tight_layout()
    fig.savefig(salida / 'comparacion_norma_seis_caras.png', dpi=180, bbox_inches='tight')
    plt.close(fig)

    # Las barras muestran diferencia absoluta respecto a la referencia, no precision verdadera.
    error_antes = [abs(dic[k]['error_norma_antes']) for k in orden]
    error_despues = [abs(dic[k]['error_norma_despues']) for k in orden]
    fig, ax = plt.subplots(figsize=(10,5))
    ax.bar(x-.18, error_antes, .36, label='Antes')
    ax.bar(x+.18, error_despues, .36, label='Despues')
    ax.set_xticks(x, orden)
    ax.set_ylabel('Diferencia absoluta frente a g local (m/s2)')
    ax.set_title('Seis caras: error de magnitud antes y despues de calibrar')
    ax.legend()
    ax.grid(axis='y', alpha=.2)
    fig.tight_layout()
    fig.savefig(salida / 'comparacion_error_seis_caras.png', dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10,5))
    ancho = .25
    for i,eje in enumerate(EJES):
        ax.bar(x+(i-1)*ancho, [dic[k][['ax_media','ay_media','az_media'][i]] for k in orden],
               ancho, label=eje)
    ax.axhline(0, color='black', lw=.8)
    ax.set_xticks(x, orden)
    ax.set_ylabel('Aceleracion media sin calibrar (m/s2)')
    ax.set_title('Lecturas en los tres ejes para las seis orientaciones')
    ax.legend()
    ax.grid(axis='y', alpha=.2)
    fig.tight_layout()
    fig.savefig(salida / 'medias_por_orientacion.png', dpi=180)
    plt.close(fig)

    if reposo.is_file():
        d = pd.read_csv(reposo)
        a = d[COLS].to_numpy(dtype=float)
        cal = (a-bias)/scale
        raw_norm = np.linalg.norm(a,axis=1)
        cal_norm = np.linalg.norm(cal,axis=1)
        med_raw = np.linalg.norm(a.mean(axis=0))
        med_cal = np.linalg.norm(cal.mean(axis=0))
        validacion = {
            'archivo':reposo.name,
            'muestras':len(d),
            'norma_media_original':float(med_raw),
            'norma_media_calibrada':float(med_cal),
            'error_norma_original':float(med_raw-g),
            'error_norma_calibrada':float(med_cal-g),
            'nota':'Validacion cruzada con reposo independiente. No estima error absoluto de posicion ni deriva angular.'
        }
        parametros['validacion_reposo'] = validacion
        print(f'\nREPOSO INDEPENDIENTE: {reposo.name}, {len(d)} muestras')
        print(f' Norma del vector medio: antes={med_raw:.6f}, despues={med_cal:.6f} m/s2')
        print(f' Diferencia con g: antes={med_raw-g:+.6f}, despues={med_cal-g:+.6f} m/s2')
        paso = max(1,len(d)//2500)
        ts = d['t_s'].to_numpy()[::paso]/60
        fig, ax = plt.subplots(figsize=(11,5))
        ax.plot(ts,raw_norm[::paso],label='Antes',alpha=.75)
        ax.plot(ts,cal_norm[::paso],label='Despues',alpha=.85)
        ax.axhline(g,color='black',ls='--',label=f'g local={g:.4f}')
        ax.set_xlabel('Tiempo (minutos)')
        ax.set_ylabel('Norma de aceleracion (m/s2)')
        ax.set_title('Reposo: validacion independiente de la calibracion de seis caras')
        ax.legend()
        ax.grid(alpha=.2)
        fig.tight_layout()
        fig.savefig(salida / 'validacion_reposo_009.png',dpi=180)
        plt.close(fig)
    else:
        print(f'\nNo se encontro {reposo}. Se omite la validacion independiente de reposo.')

    with open(salida / 'parametros_calibracion.json', 'w', encoding='utf-8') as f:
        json.dump(parametros, f, indent=2, ensure_ascii=False)
    print(f'\nArchivos guardados en: {salida}')

if __name__ == '__main__':
    p=argparse.ArgumentParser(description='Calibracion diagonal del acelerometro por seis caras')
    raiz = Path(__file__).resolve().parent.parent
    # Si el script se ejecuta fuera del repositorio, permite pasar las rutas por argumento.
    p.add_argument('--directorio', type=Path, default=raiz/'datos'/'procesados', help='Carpeta con datos_010..015_fisico.csv')
    p.add_argument('--salida', type=Path, default=raiz/'resultados'/'calibracion', help='Carpeta de resultados')
    p.add_argument('--reposo', type=Path, default=raiz/'datos'/'procesados'/'datos_009_fisico.csv', help='CSV de reposo independiente')
    p.add_argument('--gravedad', type=float, default=GRAVEDAD_QUITO_MS2, help='Gravedad de referencia (m/s2), defecto: Quito 9.7726')
    args=p.parse_args()
    procesar(args.directorio,args.salida,args.reposo,args.gravedad)

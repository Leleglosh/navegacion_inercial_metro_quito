"""
Este script implementa:
1. Gráficas de aceleración y velocidad angular en el tiempo.
2. Comparación de integración numérica (Euler vs Trapecio).
3. Superposición de marcas de eventos (pulsador).
4. Guardado automático de imágenes en la carpeta 'resultados/'.
"""

import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def graficar_sensores_raw(df, ruta_guardado="resultados/sensores_raw.png"):
    """
    Genera una figura de dos paneles: Aceleraciones (m/s²) y Giroscopio (deg/s).
    """
    os.makedirs(os.path.dirname(ruta_guardado), exist_ok=True)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    
    # Panel 1: Aceleración
    ax1.plot(df['t_s'], df['ax'], label='ax', color='r', alpha=0.8)
    ax1.plot(df['t_s'], df['ay'], label='ay', color='g', alpha=0.8)
    ax1.plot(df['t_s'], df['az'], label='az', color='b', alpha=0.8)
    ax1.set_ylabel('Aceleración [m/s²]')
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(loc='upper right')
    ax1.set_title('Mediciones de la IMU en Unidades Físicas')
    
    # Panel 2: Giroscopio
    ax2.plot(df['t_s'], df['gx'], label='gx', color='r', alpha=0.8)
    ax2.plot(df['t_s'], df['gy'], label='gy', color='g', alpha=0.8)
    ax2.plot(df['t_s'], df['gz'], label='gz', color='b', alpha=0.8)
    ax2.set_xlabel('Tiempo [s]')
    ax2.set_ylabel('Vel. Angular [°/s]')
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(loc='upper right')
    
    plt.tight_layout()
    plt.savefig(ruta_guardado, dpi=300)
    print(f"[OK] Gráfica de sensores guardada en: {ruta_guardado}")
    plt.close()

def graficar_integracion(df, ruta_guardado="resultados/perfil_integracion.png"):
    """
    Genera un gráfico comparativo de Aceleración Neta, Velocidad y Posición estimada.
    """
    os.makedirs(os.path.dirname(ruta_guardado), exist_ok=True)
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    
    # Aceleración neta
    if 'az_neta' in df.columns:
        ax1.plot(df['t_s'], df['az_neta'], color='black', label='az neta')
    ax1.set_ylabel('Acel. Neta [m/s²]')
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(loc='upper right')
    ax1.set_title('Estimación de Cinematática Vertical (Integración Numérica)')
    
    # Velocidad (Euler vs Trapecio)
    if 'v_euler' in df.columns and 'v_trapecio' in df.columns:
        ax2.plot(df['t_s'], df['v_euler'], label='Euler', color='orange', linestyle='--')
        ax2.plot(df['t_s'], df['v_trapecio'], label='Trapecio', color='blue', alpha=0.7)
    ax2.set_ylabel('Velocidad [m/s]')
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(loc='upper right')
    
    # Posición / Desplazamiento
    if 'z_euler' in df.columns and 'z_trapecio' in df.columns:
        ax3.plot(df['t_s'], df['z_euler'], label='Euler', color='orange', linestyle='--')
        ax3.plot(df['t_s'], df['z_trapecio'], label='Trapecio', color='green', alpha=0.7)
    ax3.set_xlabel('Tiempo [s]')
    ax3.set_ylabel('Posición Z [m]')
    ax3.grid(True, linestyle='--', alpha=0.6)
    ax3.legend(loc='upper right')
    
    # Si existen marcas del pulsador, dibujarlas como líneas verticales rojas
    if 'btn_edge' in df.columns:
        marcas = df[df['btn_edge'] == 1]
        for t_marca in marcas['t_s']:
            ax1.axvline(x=t_marca, color='red', linestyle=':', alpha=0.8)
            ax2.axvline(x=t_marca, color='red', linestyle=':', alpha=0.8)
            ax3.axvline(x=t_marca, color='red', linestyle=':', alpha=0.8)
            
    plt.tight_layout()
    plt.savefig(ruta_guardado, dpi=300)
    print(f"[OK] Gráfica de integración guardada en: {ruta_guardado}")
    plt.close()

if __name__ == "__main__":
    print("--- Ejecutando prueba autónoma de graficas.py ---")
    
    # Datos de prueba sintéticos
    t = np.linspace(0, 10, 500)
    df_prueba = pd.DataFrame({
        't_s': t,
        'ax': np.sin(t) * 0.1,
        'ay': np.cos(t) * 0.1,
        'az': -9.780 + np.sin(t) * 0.5,
        'gx': np.random.normal(0, 0.2, 500),
        'gy': np.random.normal(0, 0.2, 500),
        'gz': np.random.normal(0, 0.2, 500),
        'az_neta': np.sin(t) * 0.5,
        'v_euler': -0.5 * np.cos(t) + 0.5,
        'v_trapecio': -0.5 * np.cos(t) + 0.5,
        'z_euler': -0.5 * np.sin(t) + 0.5 * t,
        'z_trapecio': -0.5 * np.sin(t) + 0.5 * t,
        'btn_edge': np.where((t > 4.9) & (t < 5.1), 1, 0)
    })
    
    graficar_sensores_raw(df_prueba, "resultados/prueba_sensores.png")
    graficar_integracion(df_prueba, "resultados/prueba_integracion.png")

"""
Este script implementa:
1. Resta de la gravedad estática local de Quito (9.780 m/s²).
2. Integración numérica por Método de Euler Rectangular (1er orden).
3. Integración numérica por Regla del Trapecio (2do orden).
4. Estimación de velocidad (m/s) y posición (m).
"""

import numpy as np
import pandas as pd

def remover_gravedad_estatica(az_corregido, g_quito=9.780):
    """
    Resta la aceleración de la gravedad estática de Quito del eje vertical (Z).
    Parámetros:
        az_corregido (np.array o pd.Series): Aceleración en Z ya calibrada en m/s².
        g_quito (float): Gravedad local de Quito en m/s² (default: 9.780).        
    Retorna:
        np.array: Aceleración neta (movimiento dinámico puro sin gravedad).
    """
    # En reposo, az es aproximadamente -9.780 m/s² (o +9.780 según la orientación del sensor).
    # AJUSTE FUTURO: Si el sensor está boca arriba y mide -9.780 m/s², se suma g_quito.
    # Si mide +9.780 m/s², se resta g_quito.
    # Aquí sumamos g_quito asumiendo az estático ≈ -9.780 m/s².
    az_neta = az_corregido + g_quito
    
    return az_neta

def integrar_euler(t, a):
    """
    Calcula velocidad y posición mediante el método de Euler (rectángulos a la izquierda).
    Fórmulas: 
        v[i] = v[i-1] + a[i-1] * dt
        z[i] = z[i-1] + v[i-1] * dt
        
    Parámetros:
        t (np.array): Arreglo de tiempo en segundos.
        a (np.array): Aceleración neta en m/s².
        
    Retorna:
        v (np.array): Velocidad estimada en m/s.
        z (np.array): Posición/Desplazamiento estimado en metros.
    """
    n = len(t)
    v = np.zeros(n)
    z = np.zeros(n)
    
    for i in range(1, n):
        dt = t[i] - t[i-1]
        # Evitar saltos de tiempo anómalos si se pierde un paquete
        if dt <= 0:
            dt = 1e-6
            
        v[i] = v[i-1] + a[i-1] * dt
        z[i] = z[i-1] + v[i-1] * dt
        
    return v, z

def integrar_trapecio(t, a):
    """
    Calcula velocidad y posición mediante la Regla del Trapecio.
    Fórmulas:
        v[i] = v[i-1] + 0.5 * (a[i] + a[i-1]) * dt
        z[i] = z[i-1] + 0.5 * (v[i] + v[i-1]) * dt
        
    Parámetros:
        t (np.array): Arreglo de tiempo en segundos.
        a (np.array): Aceleración neta en m/s².
        
    Retorna:
        v (np.array): Velocidad estimada en m/s.
        z (np.array): Posición/Desplazamiento estimado en metros.
    """
    n = len(t)
    v = np.zeros(n)
    z = np.zeros(n)
    
    for i in range(1, n):
        dt = t[i] - t[i-1]
        if dt <= 0:
            dt = 1e-6
            
        # Integración de la aceleración para obtener velocidad
        v[i] = v[i-1] + 0.5 * (a[i] + a[i-1]) * dt
        # Integración de la velocidad para obtener posición
        z[i] = z[i-1] + 0.5 * (v[i] + v[i-1]) * dt
        
    return v, z

def comparar_metodos_integracion(df_procesado, columna_accel='az_neta'):
    """
    Ejecuta ambos métodos numéricos (Euler vs Trapecio) sobre un DataFrame
    y añade las columnas resultantes para su análisis comparativo.
    """
    df_res = df_procesado.copy()
    t = df_res['t_s'].values
    a = df_res[columna_accel].values
    
    # Calcular con Euler
    v_euler, z_euler = integrar_euler(t, a)
    df_res['v_euler'] = v_euler
    df_res['z_euler'] = z_euler
    
    # Calcular con Trapecio
    v_trap, z_trap = integrar_trapecio(t, a)
    df_res['v_trapecio'] = v_trap
    df_res['z_trapecio'] = z_trap
    
    # Diferencia entre métodos (error del método numérico)
    df_res['diff_v'] = np.abs(v_trap - v_euler)
    df_res['diff_z'] = np.abs(z_trap - z_euler)
    
    return df_res

if __name__ == "__main__":
    print("--- Ejecutando prueba autónoma de integracion.py ---")
    
    # Crear un perfil sintético de aceleración de 10 segundos a 200 Hz (dt = 0.005 s)
    dt_sim = 0.005
    t_sim = np.arange(0, 10.0, dt_sim)
    
    # Simular una aceleración senoidal en Z (un movimiento de subida y bajada)
    a_sim = 0.5 * np.sin(2 * np.pi * 0.2 * t_sim)
    
    df_sim = pd.DataFrame({'t_s': t_sim, 'az_neta': a_sim})
    
    # Ejecutar comparación de integración
    df_resultado = comparar_metodos_integracion(df_sim, columna_accel='az_neta')
    
    print("\n[OK] Integración numérica completada con éxito.")
    print("Resumen de resultados al segundo 10:")
    print(f"- Velocidad final (Euler):    {df_resultado['v_euler'].iloc[-1]:.6f} m/s")
    print(f"- Velocidad final (Trapecio): {df_resultado['v_trapecio'].iloc[-1]:.6f} m/s")
    print(f"- Posición final (Euler):     {df_resultado['z_euler'].iloc[-1]:.6f} m")
    print(f"- Posición final (Trapecio):  {df_resultado['z_trapecio'].iloc[-1]:.6f} m")
    print(f"- Máxima diferencia en Z:     {df_resultado['diff_z'].max():.6f} m")

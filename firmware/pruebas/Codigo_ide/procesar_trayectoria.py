import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import cumulative_trapezoid, cumulative_simpson
from io_log import load_session, G_QUITO

def altitude_from_pressure(P_pa, T_kelvin=288.15):
    valid = ~np.isnan(P_pa)
    p_ref = np.median(P_pa[valid][:20])
    H = 8.314462 * T_kelvin / (0.0289644 * G_QUITO)
    h = -H * np.log(P_pa / p_ref)
    return h

def zupt_velocity(a_long, t, still_mask):
    """Integra aceleración longitudinal y corrige deriva lineal entre paradas (ZUPT)."""
    v = np.zeros_like(a_long)
    moving = ~still_mask
    starts = np.flatnonzero(np.diff(np.r_[0, moving.astype(int)]) == 1)
    ends   = np.flatnonzero(np.diff(np.r_[moving.astype(int), 0]) == -1)

    for i0, i1 in zip(starts, ends):
        if i1 <= i0:
            continue
        seg = cumulative_trapezoid(a_long[i0:i1+1], t[i0:i1+1], initial=0.0)
        # Eliminar deriva lineal asumiendo v(t_final) = 0 en estación
        drift = seg[-1] * (t[i0:i1+1] - t[i0]) / (t[i1] - t[i0])
        v[i0:i1+1] = seg - drift
    return v

def process_metro_or_elevator(prefix, mode='metro'):
    df, info = load_session(prefix)
    t = df['t'].to_numpy()
    dt = np.mean(np.diff(t))

    # Eventos marcados con el pulsador
    btn_times = t[df['btn_edge']]
    print(f"Archivo {prefix}: {len(btn_times)} eventos de pulsador detectados.")

    # Crear máscara de reposo usando los pares de pulsaciones (llegada -> salida)
    still = np.zeros(len(t), dtype=bool)
    still[t < 10.0] = True  # primeros 10 s de reposo inicial
    for t_in, t_out in zip(btn_times[0::2], btn_times[1::2]):
        still |= (t >= t_in + 0.5) & (t <= t_out - 0.5)

    if mode == 'ascensor':
        # Sustraer gravedad local en eje Z
        az = df['az'].to_numpy() - np.mean(df['az'].to_numpy()[still])
        vz = zupt_velocity(az, t, still)
        z_imu = cumulative_trapezoid(vz, t, initial=0.0)
        z_baro = altitude_from_pressure(df['P_pa'].to_numpy())

        plt.figure(figsize=(10, 5))
        plt.plot(t, z_imu, label='Altura IMU + ZUPT (m)')
        plt.scatter(t, z_baro, s=5, color='orange', alpha=0.6, label='Altura Barómetro (m)')
        for bt in btn_times:
            plt.axvline(bt, color='red', linestyle='--', alpha=0.4)
        plt.xlabel('Tiempo (s)')
        plt.ylabel('Desplazamiento vertical (m)')
        plt.title(f'Validación en Ascensor - {prefix}')
        plt.legend()
        plt.grid(True)
        plt.show()

    elif mode == 'metro':
        # Aceleración longitudinal eje X corregida por sesgo inicial en reposo
        ax = df['ax'].to_numpy() - np.mean(df['ax'].to_numpy()[still])
        vx = zupt_velocity(ax, t, still)
        dist_trap = cumulative_trapezoid(vx, t, initial=0.0)
        dist_simp = cumulative_simpson(vx, x=t, initial=0.0)

        print(f"Distancia total estimada (Trapecio): {dist_trap[-1]:.2f} m")
        print(f"Distancia total estimada (Simpson):  {dist_simp[-1]:.2f} m")

        plt.figure(figsize=(10, 5))
        plt.plot(t / 60.0, vx, label='Velocidad estimada (m/s)')
        for bt in btn_times:
            plt.axvline(bt / 60.0, color='red', linestyle='--', alpha=0.4)
        plt.xlabel('Tiempo (min)')
        plt.ylabel('Velocidad (m/s)')
        plt.title(f'Perfil de Velocidad Metro de Quito - {prefix}')
        plt.legend()
        plt.grid(True)
        plt.show()

if __name__ == '__main__':
    # Ejemplo de uso una vez tengas tu archivo LOG0000.BIN y LOG0000.HDR:
    # process_metro_or_elevator('LOG0000', mode='ascensor')
    pass
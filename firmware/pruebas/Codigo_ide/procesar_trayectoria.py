import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import cumulative_trapezoid, cumulative_simpson
from io_log import load_session, G_QUITO


def altitude_from_pressure(P_pa, T_kelvin=288.15):
    """Calcula desplazamiento vertical relativo (m) a partir de la presion en Pa."""
    valid = ~np.isnan(P_pa)
    if not np.any(valid):
        return np.zeros_like(P_pa)
    p_ref = np.median(P_pa[valid][:20])
    H = 8.314462 * T_kelvin / (0.0289644 * G_QUITO)
    return -H * np.log(P_pa / p_ref)
def zupt_velocity(a_long, t, still_mask):
    """Integra aceleracion longitudinal y elimina deriva lineal entre paradas (ZUPT)."""
    v = np.zeros_like(a_long)
    moving = ~still_mask
    starts = np.flatnonzero(np.diff(np.r_[0, moving.astype(int)]) == 1)
    ends = np.flatnonzero(np.diff(np.r_[moving.astype(int), 0]) == -1)

    for i0, i1 in zip(starts, ends):
        if i1 <= i0:
            continue
        seg = cumulative_trapezoid(a_long[i0:i1 + 1], t[i0:i1 + 1], initial=0.0)
        drift = seg[-1] * (t[i0:i1 + 1] - t[i0]) / (t[i1] - t[i0])
        v[i0:i1 + 1] = seg - drift
    return v


def process_metro_or_elevator(run_id, mode='metro', folder="."):
    """
    Procesa datos_NNN.csv y calib_NNN.txt para validar ascensor o reconstruir tramo de Metro.
    """
    df, info = load_session(run_id, folder=folder)
    t = df['t'].to_numpy()

    # Instantes exactos de pulsacion del boton
    btn_times = df.loc[df['evento'], 'evento_t'].dropna().to_numpy()
    if len(btn_times) == 0:
        btn_times = t[df['evento'].to_numpy()]

    print(f"Registro {info['run_id']} | fs real: {info['fs_real_hz']:.2f} Hz | "
          f"Saltos tiempo: {info['saltos_tiempo_total']} | Eventos boton: {len(btn_times)}")

    # Construir mascara de reposo: primeros 5 s + intervalos entre pares de pulsaciones
    still = np.zeros(len(t), dtype=bool)
    still[t < min(5.0, t[-1] * 0.1)] = True
    for t_in, t_out in zip(btn_times[0::2], btn_times[1::2]):
        still |= (t >= t_in + 0.5) & (t <= t_out - 0.5)

    if mode == 'ascensor':
        az = df['az'].to_numpy() - np.mean(df['az'].to_numpy()[still])
        vz = zupt_velocity(az, t, still)
        z_imu = cumulative_trapezoid(vz, t, initial=0.0)
        z_baro = altitude_from_pressure(df['P_pa'].to_numpy())

        plt.figure(figsize=(10, 5))
        plt.plot(t, z_imu, label='Altura IMU + ZUPT (m)')
        plt.plot(t, z_baro, color='orange', alpha=0.75, label='Altura Barometro (m)')
        for bt in btn_times:
            plt.axvline(bt, color='red', linestyle='--', alpha=0.5)
        plt.xlabel('Tiempo (s)')
        plt.ylabel('Desplazamiento vertical (m)')
        plt.title(f"Validacion en Ascensor - datos_{info['run_id']}")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.show()

    elif mode == 'metro':
        ax = df['ax'].to_numpy() - np.mean(df['ax'].to_numpy()[still])
        vx = zupt_velocity(ax, t, still)
        dist_trap = cumulative_trapezoid(vx, t, initial=0.0)
        dist_simp = cumulative_simpson(vx, x=t, initial=0.0)

        print(f"Distancia total estimada (Trapecio): {dist_trap[-1]:.2f} m")
        print(f"Distancia total estimada (Simpson):  {dist_simp[-1]:.2f} m")

        plt.figure(figsize=(10, 5))
        plt.plot(t, vx, label='Velocidad estimada (m/s)')
        for bt in btn_times:
            plt.axvline(bt, color='red', linestyle='--', alpha=0.5)
        plt.xlabel('Tiempo (s)')
        plt.ylabel('Velocidad (m/s)')
        plt.title(f"Perfil de Velocidad - datos_{info['run_id']}")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.show()


if __name__ == '__main__':
    # Cambia el numero (ej. 1 para datos_001.csv) y el modo ('ascensor' o 'metro')
    process_metro_or_elevator(1, mode='metro')
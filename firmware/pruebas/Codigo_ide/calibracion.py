import numpy as np
from scipy import signal, optimize
from io_log import load_session, G_QUITO


def calibrate_six_faces(face_means, g=G_QUITO):
    """
    Calibración estática por método de 6 caras.
    face_means: dict {'+x': [ax,ay,az], '-x': ..., '+y': ..., '-y': ..., '+z': ..., '-z': ...}
    en m/s^2 sin calibrar.
    """
    M = np.column_stack([
        (np.asarray(face_means['+' + k]) - np.asarray(face_means['-' + k])) / (2.0 * g)
        for k in 'xyz'
    ])
    b = np.mean([np.asarray(face_means[s + k]) for s in '+-' for k in 'xyz'], axis=0)
    A = np.linalg.inv(M)
    return A, b


def refine_calibration(A_init, b_init, face_means_list, g=G_QUITO):
    """Refinamiento por mínimos cuadrados (>= 12 orientaciones) sobre la norma de gravedad."""
    F = np.asarray(face_means_list)

    def res(p):
        A = p[:9].reshape(3, 3)
        bb = p[9:]
        return np.linalg.norm((A @ (F - bb).T).T, axis=1) - g

    sol = optimize.least_squares(res, np.r_[A_init.ravel(), b_init])
    return sol.x[:9].reshape(3, 3), sol.x[9:]


def apply_accel_cal(acc_raw, A, b):
    return (A @ (acc_raw - b).T).T


def allan_variance(omega, fs):
    """Calcula la desviación de Allan solapada para análisis de ruido estocástico."""
    dt = 1.0 / fs
    theta = np.cumsum(omega) * dt
    N = len(theta)
    max_m = max(10, N // 10)
    m_vals = np.unique(np.logspace(0, np.log10(max_m), 60).astype(int))
    taus, adevs = [], []
    for m in m_vals:
        if 2 * m >= N:
            continue
        tau = m * dt
        diff = theta[2 * m:] - 2 * theta[m:-m] + theta[:-2 * m]
        avar = np.sum(diff ** 2) / (2.0 * (tau ** 2) * (N - 2 * m))
        taus.append(tau)
        adevs.append(np.sqrt(avar))
    return np.array(taus), np.array(adevs)


def analyze_static_run(run_id, folder="."):
    """Analiza un registro en reposo (datos_NNN.csv) y guarda sesgos, PSD y Allan."""
    df, info = load_session(run_id, folder=folder)
    print("Resumen archivo:", info)

    # Si el registro dura más de 30 min, descartar primeros 15 min de calentamiento
    df_clean = df[df['t'] > 900].copy() if df['t'].max() > 1800 else df.copy()
    fs = info['fs_real_hz']

    gyro_bias = df_clean[['gx', 'gy', 'gz']].mean().to_numpy()
    accel_mean = df_clean[['ax', 'ay', 'az']].mean().to_numpy()
    print("Sesgo giroscopio (rad/s):", gyro_bias)
    print("Media acelerómetro en reposo (m/s^2):", accel_mean)

    nperseg = min(len(df_clean), max(64, int(fs * 10)))
    f_psd, psd_ax = signal.welch(df_clean['ax'].to_numpy(), fs=fs, nperseg=nperseg)
    taus, adev_gz = allan_variance(df_clean['gz'].to_numpy(), fs)

    out_name = f"calibracion_{info['run_id']}.npz"
    np.savez(
        out_name,
        gyro_bias=gyro_bias,
        accel_mean=accel_mean,
        f_psd=f_psd,
        psd_ax=psd_ax,
        taus=taus,
        adev_gz=adev_gz
    )
    print(f"Resultados guardados en {out_name}")


if __name__ == '__main__':
    # Cambia el número según tu archivo (ej. 1 para datos_001.csv)
    analyze_static_run(1)
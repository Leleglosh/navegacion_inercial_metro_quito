import numpy as np
from scipy import signal, optimize
from io_log import load_session, G_QUITO

def calibrate_six_faces(face_means, g=G_QUITO):
    """
    face_means: dict {'+x': [ax,ay,az], '-x': ..., '+y': ..., '-y': ..., '+z': ..., '-z': ...}
    en m/s^2 sin calibrar.
    """
    M = np.column_stack([
        (face_means['+' + k] - face_means['-' + k]) / (2.0 * g)
        for k in 'xyz'
    ])
    b = np.mean([face_means[s + k] for s in '+-' for k in 'xyz'], axis=0)
    A = np.linalg.inv(M)
    return A, b

def apply_accel_cal(acc_raw, A, b):
    return (A @ (acc_raw - b).T).T

def allan_variance(omega, fs):
    """Calcula la desviación de Allan solapada para análisis de ruido (Exp 1)."""
    dt = 1.0 / fs
    theta = np.cumsum(omega) * dt
    N = len(theta)
    max_m = N // 10
    m_vals = np.unique(np.logspace(0, np.log10(max_m), 60).astype(int))
    taus, adevs = [], []
    for m in m_vals:
        tau = m * dt
        diff = theta[2*m:] - 2*theta[m:-m] + theta[:-2*m]
        avar = np.sum(diff**2) / (2.0 * (tau**2) * (N - 2*m))
        taus.append(tau)
        adevs.append(np.sqrt(avar))
    return np.array(taus), np.array(adevs)

def analyze_static_run(prefix):
    df, info = load_session(prefix)
    print("Resumen archivo:", info)

    # Descartar primeros 15 min de calentamiento térmico si dura > 30 min
    df_clean = df[df['t'] > 900].copy() if df['t'].max() > 1800 else df.copy()
    fs = info['fs_real_hz']

    # Sesgo medio del giroscopio
    gyro_bias = df_clean[['gx', 'gy', 'gz']].mean().to_numpy()
    print("Sesgo giroscopio (rad/s):", gyro_bias)

    # PSD de Welch para acelerómetro X
    f_psd, psd_ax = signal.welch(df_clean['ax'], fs=fs, nperseg=int(fs*10))
    # Varianza de Allan para giroscopio Z
    taus, adev_gz = allan_variance(df_clean['gz'].to_numpy(), fs)

    np.savez('calibracion_estatica.npz', gyro_bias=gyro_bias, f_psd=f_psd, psd_ax=psd_ax, taus=taus, adev_gz=adev_gz)
    print("Resultados guardados en calibracion_estatica.npz")
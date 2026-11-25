
import pandas as pd
import numpy as np

df = pd.read_csv("datos/crudos/datos_001.csv")

# Tiempos de adquisicion en segundos
t = df["t_us"].to_numpy() / 1e6

intervalos = np.diff(t)
duracion = t[-1] - t[0]

frecuencia = (len(t) - 1) / duracion

print("=== ANALISIS DEL REGISTRO ===")
print("Muestras:", len(df))
print(f"Duracion: {duracion:.3f} s")
print(f"Frecuencia media: {frecuencia:.2f} Hz")
print(f"Intervalo promedio: {np.mean(intervalos)*1000:.3f} ms")
print(f"Intervalo maximo: {np.max(intervalos)*1000:.3f} ms")

print("Intervalos mayores a 15 ms:",
      np.sum(intervalos > 0.015))

print("Saltos de tiempo acumulados:",
      df["saltos_tiempo"].iloc[-1])

print("Fallos I2C acumulados:",
      df["fallos_i2c"].iloc[-1])

print("Eventos registrados:",
      int(df["evento"].sum()))

print("\nFilas con eventos:")
print(df.loc[df["evento"] == 1,
             ["t_us", "evento_t_us", "seq"]])

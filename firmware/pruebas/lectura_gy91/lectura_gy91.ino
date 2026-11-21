
#include <Wire.h>
#include "esp_timer.h"

// Direcciones detectadas en tu prueba
const uint8_t MPU = 0x68;
const uint8_t BMP = 0x76;

// Lee varios bytes consecutivos del sensor
bool leerBytes(uint8_t dir, uint8_t reg,
               uint8_t *datos, uint8_t cantidad) {

  Wire.beginTransmission(dir);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0)
    return false;

  if (Wire.requestFrom(dir, cantidad) != cantidad)
    return false;

  for (int i = 0; i < cantidad; i++) {
    datos[i] = Wire.read();
  }

  return true;
}

// Escribe un valor en un registro
bool escribirRegistro(uint8_t dir, uint8_t reg,
                      uint8_t valor) {
  Wire.beginTransmission(dir);
  Wire.write(reg);
  Wire.write(valor);

  return Wire.endTransmission() == 0;
}

// Une dos bytes en un entero con signo
int16_t unir16(uint8_t alto, uint8_t bajo) {
  return (int16_t)((uint16_t(alto) << 8) | bajo);
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Wire.begin(21, 22);
  Wire.setClock(100000);

  // Identificar los dos chips
  uint8_t idMPU, idBMP;

  if (!leerBytes(MPU, 0x75, &idMPU, 1) ||
      !leerBytes(BMP, 0xD0, &idBMP, 1)) {
    Serial.println("ERROR: no se pueden leer los IDs");
    while (true) delay(1000);
  }

  Serial.printf("# MPU ID: 0x%02X\n", idMPU);
  Serial.printf("# BMP ID: 0x%02X\n", idBMP);

  if ((idMPU != 0x70 && idMPU != 0x71) || idBMP != 0x58) {
    Serial.println("# IDs diferentes a los esperados");
    Serial.println("# Revisar el modelo antes de continuar");
    while (true) delay(1000);
  }

  // Despertar y configurar MPU-9250
  bool ok = escribirRegistro(MPU, 0x6B, 0x01);
  delay(100);

  ok = escribirRegistro(MPU, 0x1A, 0x03) && ok;
  ok = escribirRegistro(MPU, 0x19, 0x09) && ok;
  ok = escribirRegistro(MPU, 0x1B, 0x00) && ok;
  ok = escribirRegistro(MPU, 0x1C, 0x00) && ok;
  ok = escribirRegistro(MPU, 0x1D, 0x03) && ok;

  // Configurar BMP280
  ok = escribirRegistro(BMP, 0xF5, 0x00) && ok;
  ok = escribirRegistro(BMP, 0xF4, 0x27) && ok;

  if (!ok) {
    Serial.println("# ERROR configurando sensores");
    while (true) delay(1000);
  }

  delay(100);

  Serial.println("# Sensores configurados");
  Serial.println(
    "t_us,ax_raw,ay_raw,az_raw,"
    "gx_raw,gy_raw,gz_raw,p_raw,t_raw"
  );
}

void loop() {
  uint8_t imu[14];
  uint8_t baro[6];

  // Marca de tiempo en microsegundos (64 bits)
  int64_t tiempo = esp_timer_get_time();

  // Leer acelerometro, temperatura IMU y giroscopio
  bool okIMU = leerBytes(MPU, 0x3B, imu, 14);

  // Leer presion y temperatura crudas
  bool okBMP = leerBytes(BMP, 0xF7, baro, 6);

  if (!okIMU || !okBMP) {
    Serial.println("# ERROR: lectura incompleta");
    delay(100);
    return;
  }

  int16_t ax = unir16(imu[0], imu[1]);
  int16_t ay = unir16(imu[2], imu[3]);
  int16_t az = unir16(imu[4], imu[5]);

  int16_t gx = unir16(imu[8], imu[9]);
  int16_t gy = unir16(imu[10], imu[11]);
  int16_t gz = unir16(imu[12], imu[13]);

  uint32_t presionRaw =
      (uint32_t(baro[0]) << 12) |
      (uint32_t(baro[1]) << 4) |
      (baro[2] >> 4);

  uint32_t temperaturaRaw =
      (uint32_t(baro[3]) << 12) |
      (uint32_t(baro[4]) << 4) |
      (baro[5] >> 4);

  Serial.printf(
    "%lld,%d,%d,%d,%d,%d,%d,%lu,%lu\n",
    (long long)tiempo,
    ax, ay, az, gx, gy, gz,
    (unsigned long)presionRaw,
    (unsigned long)temperaturaRaw
  );

  delay(100); // Frecuencia aproximada de prueba
}

/*
  Proyecto: Navegacion inercial - primer registrador de datos crudos
  Hardware verificado por el grupo:
    ESP32-WROOM-32D (ESP32 Dev Module)
    GY-91 por I2C: MPU compatible ID 0x70 en 0x68; BMP280 ID 0x58 en 0x76
    Lector microSD SPI (modulo probado previamente)
    Pulsador momentaneo entre GPIO27 y GND

  Registro de prueba: 60 segundos, frecuencia OBJETIVO de 100 Hz.
  Archivos creados (sin sobrescribir anteriores):
    /datos_001.csv, /calib_001.txt; siguientes ejecuciones usan 002, 003, etc.

  IMPORTANTE:
  - Se guardan valores RAW, NO se resta la gravedad ni se filtra nada.
  - Este prototipo no garantiza 100 Hz sin perdidas: verificar el CSV en Python.
  - Al terminar aparece "REGISTRO FINALIZADO" y se cierra el archivo.
  - No retirar la tarjeta durante la grabacion.
*/

#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include "esp_timer.h"

// 1. Conexiones
constexpr int PIN_SDA = 21;
constexpr int PIN_SCL = 22;
constexpr uint8_t DIR_MPU = 0x68;
constexpr uint8_t DIR_BMP = 0x76;

constexpr int PIN_SD_CS   = 13;
constexpr int PIN_SD_SCK  = 18;
constexpr int PIN_SD_MISO = 19;
constexpr int PIN_SD_MOSI = 23;

constexpr int PIN_BOTON = 27;

// 2. Parametros del experimento
const int64_t PERIODO_US = 9500;                         // 100 Hz objetivo
constexpr int64_t DURACION_PRUEBA_US = 60000000LL;      // 60 segundos
constexpr int64_t REBOTE_BOTON_US = 30000LL;            // 30 ms
constexpr int64_t INTERVALO_FLUSH_US = 1000000LL;       // 1 segundo
constexpr int64_t INTERVALO_INFORME_US = 5000000LL;    // 5 segundos

File archivoDatos;
bool registroFinalizado = false;

uint32_t intentos = 0;
uint32_t muestrasEscritas = 0;
uint32_t fallosI2C = 0;
uint32_t intervalosOmitidos = 0;
uint32_t eventosEscritos = 0;

int64_t inicioRegistro = 0;
int64_t proximaMuestra = 0;
int64_t ultimoFlush = 0;
int64_t ultimoInforme = 0;

// Estado del pulsador (INPUT_PULLUP)
bool ultimaLecturaBoton = HIGH;
bool estadoEstableBoton = HIGH;
bool eventoPendiente = false;
int64_t instanteUltimoCambio = 0;
int64_t instanteEvento = 0;

// 3. Lectura/escritura de registros I2C
bool leerRegistros(uint8_t dir, uint8_t reg, uint8_t *buffer, uint8_t cantidad) {
  Wire.beginTransmission(dir);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(dir, cantidad) != cantidad) return false;
  for (uint8_t i = 0; i < cantidad; ++i) {
    buffer[i] = Wire.read();
  }
  return true;
}

bool escribirRegistro(uint8_t dir, uint8_t reg, uint8_t valor) {
  Wire.beginTransmission(dir);
  Wire.write(reg);
  Wire.write(valor);
  return Wire.endTransmission() == 0;
}

int16_t enteroConSigno(uint8_t alto, uint8_t bajo) {
  return (int16_t)(((uint16_t)alto << 8) | bajo);
}

void detenerPorError(const char *mensaje) {
  Serial.print("ERROR: ");
  Serial.println(mensaje);
  if (archivoDatos) {
    archivoDatos.flush();
    archivoDatos.close();
  }
  Serial.println("Registro detenido; revisar conexiones o tarjeta.");
  while (true) delay(1000);
}

// 4. Pulsador con antirrebote por software
void actualizarBoton(int64_t ahora) {
  bool lectura = digitalRead(PIN_BOTON);
  if (lectura != ultimaLecturaBoton) {
    ultimaLecturaBoton = lectura;
    instanteUltimoCambio = ahora;
  }

  if (lectura != estadoEstableBoton &&
      ahora - instanteUltimoCambio >= REBOTE_BOTON_US) {
    estadoEstableBoton = lectura;
    if (estadoEstableBoton == LOW) {
      eventoPendiente = true;
      instanteEvento = instanteUltimoCambio;  // instante aproximado del flanco
    }
  }
}

void finalizarRegistro() {
  if (registroFinalizado) return;
  registroFinalizado = true;

  archivoDatos.flush();
  archivoDatos.close();

  int64_t duracionRealUs = esp_timer_get_time() - inicioRegistro;
  double duracionSeg = (double)duracionRealUs / 1000000.0;

  Serial.println();
  Serial.println("=== REGISTRO FINALIZADO ===");
  Serial.printf("Duracion: %.3f s\n", duracionSeg);
  Serial.printf("Intentos: %lu\n", (unsigned long)intentos);
  Serial.printf("Muestras escritas: %lu\n", (unsigned long)muestrasEscritas);
  Serial.printf("Fallos I2C: %lu\n", (unsigned long)fallosI2C);
  Serial.printf("Intervalos omitidos: %lu\n", (unsigned long)intervalosOmitidos);
  Serial.printf("Eventos escritos: %lu\n", (unsigned long)eventosEscritos);
  Serial.printf("Frecuencia media aprox.: %.2f Hz\n",
                duracionSeg > 0 ? muestrasEscritas / duracionSeg : 0.0);
  Serial.println("Archivo cerrado. Ya puedes desconectar el USB.");
}

void setup() {
  Serial.begin(115200);
  delay(1200);
  Serial.println();
  Serial.println("=== NAVEGACION INERCIAL - PRUEBA 60 s ===");

  pinMode(PIN_BOTON, INPUT_PULLUP);
  ultimaLecturaBoton = digitalRead(PIN_BOTON);
  estadoEstableBoton = ultimaLecturaBoton;

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  Wire.setTimeOut(50);

  uint8_t idMPU = 0, idBMP = 0;
  if (!leerRegistros(DIR_MPU, 0x75, &idMPU, 1) ||
      !leerRegistros(DIR_BMP, 0xD0, &idBMP, 1)) {
    detenerPorError("no se pudieron leer los identificadores I2C");
  }

  Serial.printf("MPU ID: 0x%02X\n", idMPU);
  Serial.printf("BMP ID: 0x%02X\n", idBMP);
  if ((idMPU != 0x70 && idMPU != 0x71) || idBMP != 0x58) {
    detenerPorError("identificadores diferentes a los previstos");
  }

  // MPU-6500/MPU-9250: acelerarometro +/-2g, giroscopio +/-250 deg/s
  bool ok = escribirRegistro(DIR_MPU, 0x6B, 0x01);  // salir de sleep
  delay(100);
  ok = escribirRegistro(DIR_MPU, 0x1A, 0x03) && ok;
  ok = escribirRegistro(DIR_MPU, 0x19, 0x04) && ok;
  ok = escribirRegistro(DIR_MPU, 0x1B, 0x00) && ok;
  ok = escribirRegistro(DIR_MPU, 0x1C, 0x00) && ok;
  ok = escribirRegistro(DIR_MPU, 0x1D, 0x03) && ok;

  // BMP280: temperatura y presion con sobremuestreo x1, modo normal
  ok = escribirRegistro(DIR_BMP, 0xF5, 0x00) && ok;
  ok = escribirRegistro(DIR_BMP, 0xF4, 0x27) && ok;
  if (!ok) detenerPorError("configurando los sensores");

  // Coeficientes de compensacion del BMP280: registros 0x88 a 0x9F
  uint8_t coefBMP[24];
  if (!leerRegistros(DIR_BMP, 0x88, coefBMP, sizeof(coefBMP))) {
    detenerPorError("leyendo coeficientes BMP280");
  }

  SPI.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
  if (!SD.begin(PIN_SD_CS, SPI, 4000000)) {
    detenerPorError("no se pudo inicializar la microSD");
  }
  Serial.println("MicroSD inicializada correctamente");

  // Crear pareja de archivos unica; no sobrescribir experimentos anteriores
  char rutaDatos[24];
  char rutaCalibracion[24];
  bool hayNombre = false;
  for (int numero = 1; numero <= 999; ++numero) {
    snprintf(rutaDatos, sizeof(rutaDatos), "/datos_%03d.csv", numero);
    snprintf(rutaCalibracion, sizeof(rutaCalibracion), "/calib_%03d.txt", numero);
    if (!SD.exists(rutaDatos) && !SD.exists(rutaCalibracion)) {
      hayNombre = true;
      break;
    }
  }
  if (!hayNombre) detenerPorError("no hay nombres de archivo disponibles");

  File archivoCalib = SD.open(rutaCalibracion, FILE_WRITE);
  if (!archivoCalib) detenerPorError("no se pudo crear el archivo de calibracion");
  archivoCalib.println("CONFIGURACION_REGISTRO");
  archivoCalib.print("MPU_ID=0x"); archivoCalib.println(idMPU, HEX);
  archivoCalib.print("BMP_ID=0x"); archivoCalib.println(idBMP, HEX);
  archivoCalib.println("MPU_ACCEL=+-2g");
  archivoCalib.println("MPU_GYRO=+-250_dps");
  archivoCalib.println("MPU_SMPLRT_DIV=0x04");
  archivoCalib.println("MPU_CONFIG=0x03");
  archivoCalib.println("MPU_ACCEL_CONFIG2=0x03");
  archivoCalib.println("BMP_CONFIG=0x00");
  archivoCalib.println("BMP_CTRL_MEAS=0x27");
  archivoCalib.println("PERIODO_OBJETIVO_US=9500");
  archivoCalib.println("I2C_CLOCK_HZ=400000");
  archivoCalib.println("SD_SPI_HZ=4000000");
  archivoCalib.println("DURACION_OBJETIVO_S=60");
  archivoCalib.println("TIEMPOS=MICROSEGUNDOS_DESDE_ARRANQUE");
  archivoCalib.println("CALIBRACION_FABRICA_BMP280");
  archivoCalib.println("registro,byte_hex");
  for (uint8_t i = 0; i < sizeof(coefBMP); ++i) {
    char linea[20];
    snprintf(linea, sizeof(linea), "0x%02X,0x%02X", 0x88 + i, coefBMP[i]);
    archivoCalib.println(linea);
  }
  archivoCalib.close();

  archivoDatos = SD.open(rutaDatos, FILE_WRITE);
  if (!archivoDatos) detenerPorError("no se pudo crear el CSV");
  archivoDatos.println(
    "seq,t_us,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,"
    "p_raw,t_raw,evento,evento_t_us,saltos_tiempo,fallos_i2c"
  );
  archivoDatos.flush();

  Serial.print("CSV: "); Serial.println(rutaDatos);
  Serial.print("Coeficientes y configuracion: "); Serial.println(rutaCalibracion);
  Serial.println("Iniciando adquisicion (objetivo: 100 Hz durante 60 s)...");
  Serial.println("Presiona el boton 2 o 3 veces durante la prueba.");

  inicioRegistro = esp_timer_get_time();
  proximaMuestra = inicioRegistro;  // primera muestra inmediatamente
  ultimoFlush = inicioRegistro;
  ultimoInforme = inicioRegistro;
}

void loop() {
  if (registroFinalizado) {
    delay(1000);
    return;
  }

  int64_t ahora = esp_timer_get_time();
  actualizarBoton(ahora);

  if (ahora - inicioRegistro >= DURACION_PRUEBA_US) {
    finalizarRegistro();
    return;
  }

  if (ahora >= proximaMuestra) {
    int64_t atraso = ahora - proximaMuestra;
    if (atraso >= PERIODO_US) {
      uint32_t omitidos = (uint32_t)(atraso / PERIODO_US);
      intervalosOmitidos += omitidos;
      proximaMuestra += (int64_t)omitidos * PERIODO_US;
    }
    proximaMuestra += PERIODO_US;
    intentos++;

    uint8_t datosIMU[14];
    uint8_t datosBMP[6];
    int64_t tiempoMuestra = esp_timer_get_time();
    bool okIMU = leerRegistros(DIR_MPU, 0x3B, datosIMU, 14);
    bool okBMP = leerRegistros(DIR_BMP, 0xF7, datosBMP, 6);

    if (!okIMU || !okBMP) {
      fallosI2C++;
    } else {
      int16_t ax = enteroConSigno(datosIMU[0], datosIMU[1]);
      int16_t ay = enteroConSigno(datosIMU[2], datosIMU[3]);
      int16_t az = enteroConSigno(datosIMU[4], datosIMU[5]);
      int16_t gx = enteroConSigno(datosIMU[8], datosIMU[9]);
      int16_t gy = enteroConSigno(datosIMU[10], datosIMU[11]);
      int16_t gz = enteroConSigno(datosIMU[12], datosIMU[13]);

      uint32_t presionRaw = ((uint32_t)datosBMP[0] << 12) |
                             ((uint32_t)datosBMP[1] << 4) |
                             (datosBMP[2] >> 4);
      uint32_t temperaturaRaw = ((uint32_t)datosBMP[3] << 12) |
                                 ((uint32_t)datosBMP[4] << 4) |
                                 (datosBMP[5] >> 4);

      int evento = eventoPendiente ? 1 : 0;
      int64_t instanteEventoGuardado = eventoPendiente ? instanteEvento : 0;

      char linea[192];
      int longitud = snprintf(
        linea, sizeof(linea),
        "%lu,%lld,%d,%d,%d,%d,%d,%d,%lu,%lu,%d,%lld,%lu,%lu\n",
        (unsigned long)intentos,
        (long long)tiempoMuestra,
        ax, ay, az, gx, gy, gz,
        (unsigned long)presionRaw,
        (unsigned long)temperaturaRaw,
        evento,
        (long long)instanteEventoGuardado,
        (unsigned long)intervalosOmitidos,
        (unsigned long)fallosI2C
      );
      if (longitud <= 0 || longitud >= (int)sizeof(linea)) {
        detenerPorError("la linea CSV no cabe en el buffer");
      }
      size_t guardados = archivoDatos.write((const uint8_t *)linea, longitud);
      if (guardados != (size_t)longitud) {
        detenerPorError("fallo al escribir datos en microSD");
      }
      muestrasEscritas++;
      if (eventoPendiente) {
        eventosEscritos++;
        eventoPendiente = false;
      }
    }
  }

  ahora = esp_timer_get_time();
  if (ahora - ultimoFlush >= INTERVALO_FLUSH_US) {
    archivoDatos.flush();
    ultimoFlush = esp_timer_get_time();
  }
  if (ahora - ultimoInforme >= INTERVALO_INFORME_US) {
    Serial.printf("Escritos: %lu | Fallos I2C: %lu | "
                  "Intervalos omitidos: %lu | Eventos: %lu\n",
                  (unsigned long)muestrasEscritas,
                  (unsigned long)fallosI2C,
                  (unsigned long)intervalosOmitidos,
                  (unsigned long)eventosEscritos);
    ultimoInforme = esp_timer_get_time();
  }
}

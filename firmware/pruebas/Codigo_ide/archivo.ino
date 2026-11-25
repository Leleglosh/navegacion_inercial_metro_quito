#include <Arduino.h>
#include <SPI.h>
#include <SdFat.h>
#include <WiFi.h>
#include <esp_bt.h>

// =========================================================================
// MAPA DE PINES PARA ESP32 WROOM-32D (Doble bus SPI: HSPI + VSPI)
// =========================================================================
// Bus 1 (HSPI): Sensores GY-91
#define PIN_IMU_SCK   14
#define PIN_IMU_MISO  27
#define PIN_IMU_MOSI  13
#define PIN_CS_MPU    15
#define PIN_CS_BMP    26
#define PIN_INT_DRDY  25

// Bus 2 (VSPI): Módulo lector microSD
#define PIN_SD_SCK    18
#define PIN_SD_MISO   19
#define PIN_SD_MOSI   23
#define PIN_CS_SD     5

// Interfaz de usuario
#define PIN_BTN       4
#define PIN_LED       2   // LED azul integrado en WROOM-32D

// =========================================================================
// ESTRUCTURA DEL REGISTRO BINARIO (36 BYTES EXACTOS)
// =========================================================================
typedef struct __attribute__((packed)) {
  uint32_t t_us;      // micros() en flanco DRDY
  uint16_t seq;       // Contador secuencial (detecta pérdida de paquetes)
  uint8_t  flags;     // b0: baro nuevo, b1: mag nuevo, b2: btn estado, b3: btn flanco, b4: overrun
  uint8_t  rsv;
  int16_t  a[3];      // Acelerómetro crudo (X, Y, Z)
  int16_t  g[3];      // Giroscopio crudo (X, Y, Z)
  int16_t  m[3];      // Magnetómetro crudo (X, Y, Z)
  int16_t  t_mpu;     // Temperatura interna MPU
  int32_t  p_raw;     // Presión cruda BMP280 (20 bits)
  int32_t  t_raw;     // Temperatura cruda BMP280 (20 bits)
} Rec;

static_assert(sizeof(Rec) == 36, "El registro debe medir 36 bytes");

// =========================================================================
// BUFFER CIRCULAR EN SRAM (64 KB ~ 9 segundos de respaldo continuo)
// =========================================================================
#define RING_CAP 1820  // 1820 * 36 bytes = 65,520 bytes
Rec ringBuf[RING_CAP];
volatile uint32_t headIdx = 0;
volatile uint32_t tailIdx = 0;
volatile uint32_t overruns = 0;

SPIClass spiIMU(HSPI);
SPIClass spiSD(VSPI);
SdFat sd;
FsFile dataFile;

TaskHandle_t hSampleTask = NULL;
volatile uint32_t isr_t_us = 0;
volatile bool btnEdgeFlag = false;
volatile uint32_t lastBtnUs = 0;
volatile bool stopRequested = false;

uint8_t mpuWhoAmI = 0;
uint8_t bmpChipId = 0;
uint8_t bmpCalib[24];
char filePrefix[16];

// =========================================================================
// FUNCIONES DE ACCESO SPI DE BAJO NIVEL
// =========================================================================
uint8_t readReg(uint8_t cs, uint8_t reg) {
  spiIMU.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs, LOW);
  spiIMU.transfer(reg | 0x80);
  uint8_t val = spiIMU.transfer(0x00);
  digitalWrite(cs, HIGH);
  spiIMU.endTransaction();
  return val;
}

void writeReg(uint8_t cs, uint8_t reg, uint8_t val) {
  spiIMU.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE3));
  digitalWrite(cs, LOW);
  spiIMU.transfer(reg & 0x7F);
  spiIMU.transfer(val);
  digitalWrite(cs, HIGH);
  spiIMU.endTransaction();
}

void readBurst(uint8_t cs, uint8_t startReg, uint8_t *buf, size_t len, uint32_t freqHz) {
  spiIMU.beginTransaction(SPISettings(freqHz, MSBFIRST, SPI_MODE3));
  digitalWrite(cs, LOW);
  spiIMU.transfer(startReg | 0x80);
  for (size_t i = 0; i < len; i++) {
    buf[i] = spiIMU.transfer(0x00);
  }
  digitalWrite(cs, HIGH);
  spiIMU.endTransaction();
}

void errorBlink(int code) {
  while (true) {
    for (int i = 0; i < code; i++) {
      digitalWrite(PIN_LED, HIGH); delay(150);
      digitalWrite(PIN_LED, LOW);  delay(150);
    }
    delay(1000);
  }
}

// =========================================================================
// INTERRUPCIONES (ISR)
// =========================================================================
void IRAM_ATTR isrDRDY() {
  isr_t_us = micros();
  BaseType_t xHigherPriorityTaskWoken = pdFALSE;
  if (hSampleTask != NULL) {
    vTaskNotifyGiveFromISR(hSampleTask, &xHigherPriorityTaskWoken);
    portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
  }
}

void IRAM_ATTR isrButton() {
  uint32_t now = micros();
  if ((now - lastBtnUs) > 30000) { // Antirrebote 30 ms
    btnEdgeFlag = true;
    lastBtnUs = now;
  }
}

// =========================================================================
// CONFIGURACIÓN DE SENSORES (GY-91)
// =========================================================================
bool initSensors() {
  pinMode(PIN_CS_MPU, OUTPUT); digitalWrite(PIN_CS_MPU, HIGH);
  pinMode(PIN_CS_BMP, OUTPUT); digitalWrite(PIN_CS_BMP, HIGH);
  spiIMU.begin(PIN_IMU_SCK, PIN_IMU_MISO, PIN_IMU_MOSI, -1);
  delay(50);

  // 1. Verificar MPU-9250 / MPU-6500
  writeReg(PIN_CS_MPU, 0x6B, 0x80); // Reset
  delay(100);
  writeReg(PIN_CS_MPU, 0x6B, 0x01); // Clock PLL
  writeReg(PIN_CS_MPU, 0x6A, 0x10); // Deshabilitar I2C interno (solo SPI)
  delay(20);

  mpuWhoAmI = readReg(PIN_CS_MPU, 0x75);
  if (mpuWhoAmI != 0x71 && mpuWhoAmI != 0x73 && mpuWhoAmI != 0x70) {
    return false;
  }

  // Configurar 200 Hz, DLPF ~41-44 Hz, +-4g, +-500 dps
  writeReg(PIN_CS_MPU, 0x19, 0x04); // SMPLRT_DIV = 4 -> 1000/(1+4) = 200 Hz
  writeReg(PIN_CS_MPU, 0x1A, 0x03); // CONFIG: DLPF_CFG = 3 (41 Hz)
  writeReg(PIN_CS_MPU, 0x1B, 0x08); // GYRO_CONFIG: +-500 dps
  writeReg(PIN_CS_MPU, 0x1C, 0x08); // ACCEL_CONFIG: +-4 g
  writeReg(PIN_CS_MPU, 0x1D, 0x03); // ACCEL_CONFIG2: A_DLPF_CFG = 3 (44.8 Hz)
  writeReg(PIN_CS_MPU, 0x37, 0x10); // INT_PIN_CFG: pulso 50 us / clear on read
  writeReg(PIN_CS_MPU, 0x38, 0x01); // INT_ENABLE: RAW_RDY_EN

  // 2. Verificar BMP280
  bmpChipId = readReg(PIN_CS_BMP, 0xD0);
  if (bmpChipId != 0x58) {
    return false;
  }

  // Leer 24 bytes de calibración de fábrica (0x88 a 0x9F)
  readBurst(PIN_CS_BMP, 0x88, bmpCalib, 24, 1000000);

  // Configurar BMP280: osrs_t x1, osrs_p x8, modo normal -> 0x33
  writeReg(PIN_CS_BMP, 0xF4, 0x33);
  // t_standby 0.5ms, filter x4, spi3w_en 0 -> 0x08
  writeReg(PIN_CS_BMP, 0xF5, 0x08);

  return true;
}

// =========================================================================
// TAREA NÚCLEO 1: MUESTREO ESTRICTO A 200 HZ
// =========================================================================
void taskSample(void *pv) {
  uint16_t seq = 0;
  uint8_t divBaro = 0;
  uint8_t bufMPU[14];
  uint8_t bufBMP[6];

  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (stopRequested) break;

    Rec r;
    r.t_us = isr_t_us;
    r.seq  = seq++;
    r.flags = 0;
    r.rsv   = 0;

    // Lectura rápida SPI (8 MHz) de 14 bytes: Accel(6) + Temp(2) + Gyro(6)
    readBurst(PIN_CS_MPU, 0x3B, bufMPU, 14, 8000000);
    r.a[0] = (int16_t)((bufMPU[0] << 8) | bufMPU[1]);
    r.a[1] = (int16_t)((bufMPU[2] << 8) | bufMPU[3]);
    r.a[2] = (int16_t)((bufMPU[4] << 8) | bufMPU[5]);
    r.t_mpu = (int16_t)((bufMPU[6] << 8) | bufMPU[7]);
    r.g[0] = (int16_t)((bufMPU[8] << 8) | bufMPU[9]);
    r.g[1] = (int16_t)((bufMPU[10] << 8) | bufMPU[11]);
    r.g[2] = (int16_t)((bufMPU[12] << 8) | bufMPU[13]);

    r.m[0] = r.m[1] = r.m[2] = 0;

    // Barómetro cada 5 muestras (200 Hz / 5 = 40 Hz)
    if (++divBaro >= 5) {
      divBaro = 0;
      readBurst(PIN_CS_BMP, 0xF7, bufBMP, 6, 4000000);
      r.p_raw = ((int32_t)bufBMP[0] << 12) | ((int32_t)bufBMP[1] << 4) | ((int32_t)bufBMP[2] >> 4);
      r.t_raw = ((int32_t)bufBMP[3] << 12) | ((int32_t)bufBMP[4] << 4) | ((int32_t)bufBMP[5] >> 4);
      r.flags |= 0x01;
    } else {
      r.p_raw = 0;
      r.t_raw = 0;
    }

    // Estado y flanco del pulsador
    if (digitalRead(PIN_BTN) == LOW) r.flags |= 0x04;
    if (btnEdgeFlag) {
      r.flags |= 0x08;
      btnEdgeFlag = false;
    }

    // Insertar en buffer circular
    uint32_t nextHead = (headIdx + 1) % RING_CAP;
    if (nextHead == tailIdx) {
      overruns++;
    } else {
      ringBuf[headIdx] = r;
      headIdx = nextHead;
    }
  }
  vTaskDelete(NULL);
}

// =========================================================================
// TAREA NÚCLEO 0: ESCRITURA SEGURA EN MICROSD
// =========================================================================
void taskSD(void *pv) {
  uint32_t lastSyncMs = millis();
  uint32_t btnHoldStart = 0;

  for (;;) {
    // Escribir bloques cuando haya al menos 112 registros (~4032 bytes)
    while (((headIdx + RING_CAP - tailIdx) % RING_CAP) >= 112) {
      for (int i = 0; i < 112; i++) {
        dataFile.write((uint8_t*)&ringBuf[tailIdx], sizeof(Rec));
        tailIdx = (tailIdx + 1) % RING_CAP;
      }
    }

    // Sync periódico cada 2 segundos + parpadeo de vida del LED
    if (millis() - lastSyncMs >= 2000) {
      dataFile.sync();
      lastSyncMs = millis();
      digitalWrite(PIN_LED, !digitalRead(PIN_LED));
    }

    // Detectar pulsación larga (> 3 s) para cierre ordenado
    if (digitalRead(PIN_BTN) == LOW) {
      if (btnHoldStart == 0) btnHoldStart = millis();
      if (millis() - btnHoldStart > 3000) {
        stopRequested = true;
        break;
      }
    } else {
      btnHoldStart = 0;
    }

    vTaskDelay(pdMS_TO_TICKS(5));
  }

  // Vaciar remanente del anillo y cerrar archivo
  while (tailIdx != headIdx) {
    dataFile.write((uint8_t*)&ringBuf[tailIdx], sizeof(Rec));
    tailIdx = (tailIdx + 1) % RING_CAP;
  }
  dataFile.sync();
  dataFile.close();

  // Escribir archivo .FTR con resumen
  char ftrName[24];
  snprintf(ftrName, sizeof(ftrName), "%s.FTR", filePrefix);
  FsFile ftr = sd.open(ftrName, O_WRITE | O_CREAT | O_TRUNC);
  if (ftr) {
    ftr.printf("overruns=%lu\n", overruns);
    ftr.close();
  }

  // LED fijo encendido indicando que ya se puede apagar
  digitalWrite(PIN_LED, HIGH);
  vTaskDelete(NULL);
}

// =========================================================================
// SETUP
// =========================================================================
void setup() {
  WiFi.mode(WIFI_OFF);
  btStop();

  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BTN, INPUT_PULLUP);
  digitalWrite(PIN_LED, LOW);

  // Inicializar SD en VSPI
  spiSD.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_CS_SD);
  SdSpiConfig sdCfg(PIN_CS_SD, DEDICATED_SPI, SD_SCK_MHZ(16), &spiSD);
  if (!sd.begin(sdCfg)) {
    errorBlink(2); // 2 parpadeos: fallo de microSD
  }

  // Inicializar Sensores en HSPI
  if (!initSensors()) {
    errorBlink(3); // 3 parpadeos: fallo de sensor GY-91
  }

  // Buscar nombre de archivo correlativo LOG0000 .. LOG9999
  char binName[24], hdrName[24];
  for (int n = 0; n < 10000; n++) {
    snprintf(filePrefix, sizeof(filePrefix), "LOG%04d", n);
    snprintf(binName, sizeof(binName), "%s.BIN", filePrefix);
    if (!sd.exists(binName)) break;
  }

  // Guardar encabezado .HDR con IDs y calibración de fábrica del BMP280
  snprintf(hdrName, sizeof(hdrName), "%s.HDR", filePrefix);
  FsFile hdr = sd.open(hdrName, O_WRITE | O_CREAT | O_TRUNC);
  if (!hdr) errorBlink(4);
  hdr.printf("MPU_WHO_AM_I=0x%02X\n", mpuWhoAmI);
  hdr.printf("BMP_CHIP_ID=0x%02X\n", bmpChipId);
  hdr.print("BMP_CALIB=");
  for (int i = 0; i < 24; i++) {
    hdr.printf("%02X", bmpCalib[i]);
  }
  hdr.println();
  hdr.close();

  // Abrir archivo binario principal
  dataFile = sd.open(binName, O_WRITE | O_CREAT | O_TRUNC);
  if (!dataFile) errorBlink(4);

  // Configurar interrupciones
  pinMode(PIN_INT_DRDY, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_INT_DRDY), isrDRDY, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_BTN), isrButton, FALLING);

  // Lanzar tareas en los dos núcleos
  xTaskCreatePinnedToCore(taskSample, "Sample", 4096, NULL, 5, &hSampleTask, 1);
  xTaskCreatePinnedToCore(taskSD,     "SD",     4096, NULL, 2, NULL,         0);
}

void loop() {
  vTaskDelay(portMAX_DELAY);
}
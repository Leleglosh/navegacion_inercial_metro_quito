
#include <SPI.h>
#include <SD.h>

// Pines de la microSD
const int PIN_CS = 13;
const int PIN_SCK = 18;
const int PIN_MISO = 19;
const int PIN_MOSI = 23;

bool tarjetaLista = false;

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=== PRUEBA MICROSD ===");

  // Configurar la comunicacion SPI
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_CS);

  // Iniciar tarjeta a 1 MHz para la prueba
  tarjetaLista = SD.begin(PIN_CS, SPI, 1000000);

  if (tarjetaLista) {
    Serial.println("MicroSD inicializada correctamente");

    Serial.print("Capacidad (MB): ");
    Serial.println(SD.cardSize() / (1024 * 1024));
  } else {
    Serial.println("ERROR: No se pudo iniciar microSD");
  }
}

void loop() {
  if (!tarjetaLista) {
    Serial.println("Revisar conexiones y formato FAT32");
    delay(3000);
    return;
  }

  // Abrir archivo para agregar informacion
  File archivo = SD.open("/prueba_sd.txt", FILE_APPEND);

  if (!archivo) {
    Serial.println("ERROR: No se pudo abrir el archivo");
    delay(3000);
    return;
  }

  archivo.print("Prueba de escritura. Tiempo (ms): ");
  archivo.println(millis());
  archivo.close();

  Serial.println("Datos guardados correctamente");

  // Leer el archivo
  File lectura = SD.open("/prueba_sd.txt", FILE_READ);

  if (lectura) {
    Serial.println("Primeras lineas del archivo:");

    for (int i = 0; i < 5 && lectura.available(); i++) {
      Serial.println(lectura.readStringUntil('\n'));
    }

    Serial.print("Tamano del archivo (bytes): ");
    Serial.println(lectura.size());

    lectura.close();
  } else {
    Serial.println("ERROR: No se pudo leer el archivo");
  }

  Serial.println("--------------------");
  delay(3000);
}

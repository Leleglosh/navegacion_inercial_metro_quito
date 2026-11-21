
#include <Wire.h>

void setup() {
    Serial.begin(115200);

    Wire.begin(21, 22); // SDA = 21, SCL = 22

    delay(1000);
    Serial.println("Iniciando escaneo I2C...");
}

void loop() {
    int encontrados = 0;

    Serial.println("Buscando sensores...");

    for (byte direccion = 1; direccion < 127; direccion++) {
        Wire.beginTransmission(direccion);
        byte error = Wire.endTransmission();

        if (error == 0) {
            Serial.print("Dispositivo encontrado: 0x");

            if (direccion < 16) {
                Serial.print("0");
            }

            Serial.println(direccion, HEX);
            encontrados++;
        }
    }

    Serial.print("Total: ");
    Serial.println(encontrados);
    Serial.println("--------------------");

    delay(3000);
}

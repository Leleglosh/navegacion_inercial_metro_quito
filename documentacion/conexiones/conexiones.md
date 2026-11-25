
## **Tabla A. ESP32 y GY-91 — comunicación I²C**

| ESP32                   | GY-91                | Función      |
| ----------------------- | -------------------- | ------------- |
| `<span>3V3</span>`    | `<span>3V3</span>` | Alimentación |
| `<span>GND</span>`    | `<span>GND</span>` | Tierra        |
| `<span>GPIO21</span>` | `<span>SDA</span>` | Datos I²C    |
| `<span>GPIO22</span>` | `<span>SCL</span>` | Reloj I²C    |


## **Tabla B. ESP32 y microSD — comunicación SPI**

| ESP32                   | Lector microSD        | Función                          |
| ----------------------- | --------------------- | --------------------------------- |
| `<span>GPIO13</span>` | `<span>CS</span>`   | Selección del lector             |
| `<span>GPIO18</span>` | `<span>SCK</span>`  | Reloj SPI                         |
| `<span>GPIO23</span>` | `<span>MOSI</span>` | Datos ESP32 → tarjeta            |
| `<span>GPIO19</span>` | `<span>MISO</span>` | Datos tarjeta → ESP32            |
| `<span>5V</span>`     | `<span>VCC</span>`  | Alimentación del módulo probado |
| `<span>GND</span>`    | `<span>GND</span>`  | Tierra                            |



## **Tabla C. ESP32 y pulsador**

| ESP32                   | Pulsador | Función        |
| ----------------------- | -------- | --------------- |
| `<span>GPIO27</span>` | Pata 1   | Entrada digital |
| `<span>GND</span>`    | Pata 2   | Tierra          |

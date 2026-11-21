## Entrada 001 — Adquisición de componentes

**Fecha:** 20/11/2026
**Responsables:** Stephanie Lozada
**Actividad:** Compra de los componentes para la elaboración del proyecto

### Objetivo

Adquirir los componentes necesarios para construir el prototipo.

### Componentes

- ESP32 WROOM-32D
- GY-91 (MPU-9250 y BMP280 responden por I²C)
- Lector microSD SPI
- microSD de 16 GB
- Pulsador de dos patas
- Cable micro-USB
- Protoboard y jumpers

![1795304923529](../documentacion/fotografias/1795304923529.png)

### Procedimiento

Se compararon cotizaciones de distintas tiendas de electrónica y se seleccionaron los componentes de acuerdo con los requisitos del proyecto.

### Decisiones

Se eligió un GY-91 para reunir los sensores inerciales y barométricos en una sola placa.

### Pendientes

- Comprobar comunicación I2C.
- Comprobar el lector microSD.

### Uso de IA

Se utilizó IA para comparar compatibilidad y planificar el montaje. Sus recomendaciones están pendientes de validación física.

## Entrada 002 — Identificación de componentes y preparación del ensamblaje

**Fecha:** 21 de noviembre de 2026
**Responsables:** Stephanie Lozada
**Actividad:** Inspección física de los componentes y preparación del primer montaje.

### Objetivo

Identificar los pines y las características principales de los módulos adquiridos para establecer conexiones seguras y preparar las primeras pruebas de comunicación.

### Componentes inspeccionados

- **ESP32-WROOM-32D:** placa de desarrollo de 38 pines, con puerto micro-USB y conversor USB-serie CP2102.
- **GY-91:** módulo multisensor con conexiones I²C y SPI. Se observa un circuito integrado con marcado compatible visualmente con la familia MPU-9250, pendiente de verificación electrónica.
- **Lector microSD SPI:** módulo de seis pines con regulador de 3,3 V identificado en la placa.

### Decisiones técnicas

Se utilizará comunicación I²C entre el ESP32 y el GY-91, mediante GPIO21 (SDA) y GPIO22 (SCL).

Se verificará primero la comunicación y la identidad de los sensores antes de incorporar el sistema de almacenamiento microSD.

### Evidencias

Fotografías de ambas caras del ESP32, GY-91 y lector microSD, almacenadas en `documentacion/fotografias/`.

**ESP32:**

![1795304517266](../documentacion/fotografias/1795304517266.png)

![1795304569116](../documentacion/fotografias/1795304569116.png)

**GY-91:**

![1795304634535](../documentacion/fotografias/1795304634535.png)

![1795304681153](../documentacion/fotografias/1795304681153.png)

Lector microSD:

![1795304748790](../documentacion/fotografias/1795304748790.png)

![1795304792601](../documentacion/fotografias/1795304792601.png)

### Estado

Inspección visual realizada. Pendiente de confirmar comunicación eléctrica, identificadores de sensores y adquisición de datos.

### Uso de IA

Se utilizó ChatGPT como apoyo para interpretar las etiquetas de los componentes, proponer las conexiones y elaborar un programa de identificación I²C. Las recomendaciones serán comprobadas mediante pruebas físicas y comparación con documentación técnica.

## Entrada 003 — Comunicación I²C y primera adquisición de datos

**Fecha:** 21/11/2026
**Responsable:** Stephanie Lozada

### Objetivo

Verificar la comunicación entre el ESP32 y el GY-91 e iniciar la adquisición de datos crudos.

### Problema encontrado

Inicialmente, Arduino IDE no permitía seleccionar un puerto COM, aunque el ESP32 recibía alimentación mediante USB.

### Solución

Se revisó el Administrador de dispositivos de Windows y se instaló el controlador USB-serie CP210x. Después, Windows reconoció el dispositivo y Arduino IDE permitió seleccionar el puerto correspondiente.

### Resultados de comunicación

Mediante un escáner I²C se detectaron dos direcciones:

- 0x68: posible sensor inercial MPU-9250.
- 0x76: posible sensor barométrico BMP280.

### Siguiente prueba

Leer los identificadores internos de los chips y comprobar que las mediciones crudas cambian ante movimientos controlados.

### Evidencias

- Captura de pantalla del monitor serie.

![1795303231006](../documentacion/fotografias/1795303231006.png)

- Código `escaner_i2c.ino`.
- Código `lectura_gy91.ino`.
  - Ambos se encuentran en la carpeta firmware/pruebas del proyecto
- Fotografías del montaje.

![1795304132090](../documentacion/fotografias/1795304132090.png)


![1795304333049](../documentacion/fotografias/1795304333049.jpg)

### Uso de IA

Se utilizó ChatGPT para diagnosticar el problema de comunicación USB, preparar el escáner I²C y desarrollar el código de lectura de sensores. Los resultados se comprobarán mediante la ejecución en el prototipo físico.

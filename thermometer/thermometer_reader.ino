#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHT.h>

// --- Configuración de pines ---
#define ONE_WIRE_BUS 2   // pin D2 para los dos DS18B20
#define DHTPIN 3         // pin D3 para el DHT11
#define DHTTYPE DHT11

// --- Inicialización de librerías ---
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds18b20(&oneWire);
DHT dht(DHTPIN, DHTTYPE);

// --- Variables ---
float T1, T2, TDHT, H;

// --- Setup ---
void setup() {
  Serial.begin(9600);
  ds18b20.begin();
  dht.begin();

  Serial.println(F("Sistema de medición de temperatura/humedad listo"));
}

// --- Loop principal ---
void loop() {
  // Espera un comando desde Python
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "READ") {
      // Lee los sensores
      ds18b20.requestTemperatures();
      T1 = ds18b20.getTempCByIndex(0);
      T2 = ds18b20.getTempCByIndex(1);
      TDHT = dht.readTemperature();
      H = dht.readHumidity();

      // Envía los datos en formato CSV
      // (Python los parsea fácilmente)
      Serial.print(T1, 2); Serial.print(",");
      Serial.print(T2, 2); Serial.print(",");
      Serial.print(TDHT, 2); Serial.print(",");
      Serial.println(H, 2);
    }
  }

  delay(50);  // breve pausa
}

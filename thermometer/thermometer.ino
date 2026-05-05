#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHT.h>

// ---------- CONFIGURACIÓN DS18B20 ----------
#define ONE_WIRE_BUS 2   // Pin D2 para ambos DS18B20
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ---------- CONFIGURACIÓN DHT11 ----------
#define DHTPIN 3
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  Serial.println("Lectura de sensores DS18B20 y DHT11");
  
  sensors.begin();
  dht.begin();
}

void loop() {
  // --- Lectura DS18B20 ---
  sensors.requestTemperatures();
  float temp1 = sensors.getTempCByIndex(0);
  float temp2 = sensors.getTempCByIndex(1);

  // --- Lectura DHT11 ---
  float hum = dht.readHumidity();
  float tempDHT = dht.readTemperature(); // °C

  // --- Verificar errores ---
  if (isnan(hum) || isnan(tempDHT)) {
    Serial.println("Error al leer DHT11");
  }

  // --- Mostrar resultados ---
  Serial.println("----");
  Serial.print("DS18B20 #1: "); Serial.print(temp1); Serial.println(" °C");
  Serial.print("DS18B20 #2: "); Serial.print(temp2); Serial.println(" °C");
  Serial.print("DHT11 Temp: "); Serial.print(tempDHT); Serial.println(" °C");
  Serial.print("DHT11 Humedad: "); Serial.print(hum); Serial.println(" %");
  
  delay(2000);  // espera 2 s entre lecturas
}

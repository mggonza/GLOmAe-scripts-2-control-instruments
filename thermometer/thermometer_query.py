import serial
import time

serial_comm = "/dev/ttyUSB0"
baud_rate = 9600

# --- Configuración del puerto ---
arduino = serial.Serial(serial_comm, baud_rate, timeout=2)
time.sleep(2)  # espera a que Arduino reinicie


def velocidad_sonido_agua(T):
    return 1402.388 + 5.0383 * T - 5.7991e-2 * T**2 + 3.287e-4 * T**3 - 1.398e-6 * T**4


def velocidad_sonido_aire(tdht, hum):
    return 331.3 + 0.606 * tdht + 0.0124 * hum


def leer_temperaturas():
    arduino.write(b"READ\n")
    line = arduino.readline().decode().strip()
    if line:
        try:
            t1, t2, tdht, hum = map(float, line.split(","))
            return t1, t2, tdht, hum
        except ValueError:
            return None
    return None


while True:
    data = leer_temperaturas()
    if data:
        t1, t2, tdht, hum = data
        # promedio de las sondas sumergibles
        Tagua = (t1 + t2) / 2
        c = velocidad_sonido_agua(Tagua)
        v = velocidad_sonido_aire(tdht, hum)
        print("-----------------------------------------")
        print(f"T1={t1:.2f}°C  T2={t2:.2f}°C  TDHT={tdht:.2f}°C  H={hum:.1f}%")
        print(f"T(agua)={Tagua:.2f}°C")
        print(f"Velocidad del sonido (aire): {v:.2f} m/s")
        print(f"Velocidad del sonido (agua): {c:.2f} m/s")

    time.sleep(2)

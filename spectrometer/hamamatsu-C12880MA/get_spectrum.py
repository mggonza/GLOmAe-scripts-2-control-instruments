import serial # Mantenemos pyserial
import time
import argparse
from matplotlib import pyplot as plt
from numpy.polynomial.polynomial import polyval
import numpy as np

"""
Cómo Usarlo en Ubuntu:
    1) Guarda el código como spectro_pyserial_linux.py (o el nombre que prefieras).
    2) Asegúrate de cumplir los prerrequisitos (instalar pyserial, etc., permisos dialout).
    3) Identifica el puerto correcto para tu Arduino (ej. /dev/ttyACM0).
    4) Ejecuta desde la terminal:
    # Usando el puerto por defecto /dev/ttyACM0 y tiempo de integración 1ms
    python get_spectrum.py datos_laser.txt laser

    # Especificando un puerto diferente y un tiempo de integración de 0.5ms
    python get_spectrum.py datos_led_ttyacm1.txt led --port /dev/ttyACM1 --time 0.0005

    # Usando fuente externa y puerto por defecto
    python get_spectrum.py datos_externos.txt ext
"""

# --- Constantes ---
DEFAULT_PORT_LINUX = '/dev/ttyACM0' # Puerto común para Arduino en Linux

class MicroSpec(object):
    def __init__(self, port):
        """Inicializa la conexión usando pyserial."""
        # La inicialización es la misma, solo cambia el valor de 'port'
        self._ser = serial.Serial(port, baudrate=115200, timeout=1)
        # Esperamos a que se inicialice la conexión serial
        time.sleep(1.5) # Aumentar ligeramente por si acaso en Linux
        print(f"Puerto serial {port} abierto.")

    def close(self):
        """Cierra el puerto serial."""
        if self._ser and self._ser.is_open:
            print(f"Cerrando puerto serial {self._ser.port}...")
            self._ser.close()

    def set_integration_time(self, seconds):
        """Establece el tiempo de integración."""
        # El comando y la escritura son iguales (bytes)
        cmd = "SPEC.INTEG %0.6f\n" % seconds
        print(f"Enviando comando: {cmd.strip()}") # Imprime comando sin newline
        self._ser.write(cmd.encode('utf8'))
        # Podría ser útil esperar una pequeña confirmación o simplemente un delay corto
        # self._ser.flush() # Espera a que se envíen los datos salientes
        # time.sleep(0.1)

    def read(self):
        """Lee los datos del espectro y la información de timing."""
        # Los comandos y la lectura/procesamiento son iguales (bytes)
        print("Enviando comando: SPEC.READ?")
        self._ser.write(b"SPEC.READ?\n")
        sdata = self._ser.readline() # Lee bytes hasta \n
        print(f"Recibido para sdata (bytes): {len(sdata)}")
        if not sdata:
            raise serial.SerialTimeoutException("Timeout esperando datos de espectro (sdata).")
        # Separar por coma en bytes, convertir a int
        sdata = np.array([int(p) for p in sdata.strip().split(b",")])

        print("Enviando comando: SPEC.TIMING?")
        self._ser.write(b"SPEC.TIMING?\n")
        tdata = self._ser.readline() # Lee bytes hasta \n
        print(f"Recibido para tdata (bytes): {len(tdata)}")
        if not tdata:
             raise serial.SerialTimeoutException("Timeout esperando datos de timing (tdata).")
       # Separar por coma en bytes, convertir a int
        tdata = np.array([int(p) for p in tdata.strip().split(b",")])

        return sdata, tdata

    def start_source(self, source):
        """Enciende la fuente de luz especificada."""
        # El comando y la escritura son iguales (bytes)
        cmd = "{source}.START\n".format(source=source.upper())
        print(f"Enviando comando: {cmd.strip()}")
        self._ser.write(cmd.encode('utf-8'))
        # time.sleep(0.1) # Pequeña pausa opcional

    def stop_source(self, source):
        """Apaga la fuente de luz especificada."""
        # El comando y la escritura son iguales (bytes)
        cmd = "{source}.STOP\n".format(source=source.upper())
        print(f"Enviando comando: {cmd.strip()}")
        self._ser.write(cmd.encode('utf-8'))
        # time.sleep(0.1) # Pequeña pausa opcional


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Controla espectrómetro MicroSpec vía Arduino y pyserial en Linux.')
    parser.add_argument('filename', type=str, help='Nombre del archivo de salida')
    parser.add_argument('source', type=str.lower, choices=['laser', 'led', 'ext'], help='Fuente a utilizar (laser, led, ext)')
    # --- Argumento añadido para el puerto ---
    parser.add_argument('--port', type=str, default=DEFAULT_PORT_LINUX,
                        help=f'Puerto serial del Arduino (ej. /dev/ttyACM0). Default: {DEFAULT_PORT_LINUX}')
    # --- Argumento añadido para tiempo de integración (opcional pero útil) ---
    parser.add_argument('--time', type=float, default=1e-3, # Default 1ms
                        help='Tiempo de integración en segundos (ej. 0.001 para 1ms). Default: 1e-3')

    args = parser.parse_args()

    delimiter = '\t'
    filename = args.filename
    source = args.source
    port = args.port # Usar el puerto de los argumentos
    integration_time = args.time # Usar tiempo de los argumentos

    spec = None # Inicializar a None para el bloque finally
    try:
        print(f"Intentando conectar al puerto: {port}")
        # --- Usar el puerto especificado en los argumentos ---
        spec = MicroSpec(port)

        # Establecer tiempo de integración
        spec.set_integration_time(integration_time)
        time.sleep(0.2) # Pequeña pausa tras configurar

        # Encender fuente si es necesario
        if source != 'ext':
            print(f"Encendiendo fuente: {source}...")
            spec.start_source(source)
            time.sleep(2)   # Dar tiempo a que la luz/fuente se estabilice

        # Medir
        print('Realizando medición...')
        sdata, tdata = spec.read()
        print(f"Medición completada. Puntos espectro: {len(sdata)}, Puntos timing: {len(tdata)}")
        time.sleep(0.1) # Pausa tras leer

        # Apagar fuente si se encendió
        if source != 'ext':
            print(f"Apagando fuente: {source}...")
            spec.stop_source(source)
            time.sleep(0.1) # Pausa tras apagar

        # --- Coeficientes de calibración y procesamiento (sin cambios) ---
        a0 = 3.140535950e2
        b1 = 2.683446321
        b2 = -1.085274073e-3
        b3 = -7.935339442e-6
        b4 = 9.280578717e-9
        b5 = 6.660903356e-12
        coefficients = [a0, b1, b2, b3, b4, b5]

        # Asumiendo que sdata siempre tendrá 288 puntos si la lectura fue exitosa
        if len(sdata) == 288:
             pixel_indices = np.linspace(1, 288, 288)
             frequency_or_wavelength = polyval(pixel_indices, coefficients)
        else:
             print(f"ADVERTENCIA: Se recibieron {len(sdata)} puntos en lugar de 288. Usando índices de píxeles.")
             # Si el número de puntos varía, usa los índices como eje x
             frequency_or_wavelength = np.arange(len(sdata))


        # --- Plotting (sin cambios) ---
        print("Mostrando gráfico...")
        plt.figure(figsize=(10, 6))
        plt.plot(frequency_or_wavelength, sdata)
        plt.title(f'Espectro ({source.upper()}) - Puerto: {port}')
        plt.xlabel('Longitud de Onda (nm) o Índice de Píxel') # Ajustar según calibración
        plt.ylabel('Intensidad (unidades ADC)')
        plt.grid(True)
        plt.show()

        # --- Guardar datos (sin cambios) ---
        print(f"Guardando datos en: {filename}")
        with open(filename, 'w') as fp:
            fp.write(f"Wavelength_nm_or_Pixel{delimiter}Intensity\n") # Encabezado
            for idx in range(len(frequency_or_wavelength)):
                # Asegurarse que sdata tenga el mismo tamaño
                if idx < len(sdata):
                    fp.write(f"{frequency_or_wavelength[idx]:.4f}{delimiter}{sdata[idx]}\n")
        print("Datos guardados.")

    except serial.SerialException as e:
        # Error al abrir o comunicar con el puerto
        print(f"\nError de pyserial: {e}")
        print("Verifica:")
        print(f"- Que el puerto '{port}' sea el correcto para tu Arduino.")
        print(f"- Que tengas permisos (añade tu usuario al grupo 'dialout': sudo usermod -a -G dialout $USER, y reinicia sesión).")
        print(f"- Que ningún otro programa (como el Monitor Serie del IDE de Arduino) esté usando el puerto.")
    except serial.SerialTimeoutException as e:
        # Timeout durante la lectura (readline)
        print(f"\nError de Timeout de pyserial: {e}")
        print("El Arduino no respondió a tiempo. Verifica:")
        print(f"- Que el sketch de Arduino esté funcionando y responda a los comandos enviados ({'SPEC.READ?' if 'sdata' in str(e) else 'SPEC.TIMING?'}).")
        print(f"- Que el baudrate ({115200}) coincida.")
        print("- Que el Arduino termine sus respuestas con un caracter de nueva línea ('\\n').")
    except Exception as e:
        # Otros errores inesperados
        print(f"\nOcurrió un error inesperado: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # --- Asegurarse de cerrar el puerto ---
        if spec:
            spec.close()
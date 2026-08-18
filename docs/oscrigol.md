# Rigol MSO2102A: clase `oscrigol`

Guia breve para entender y probar la clase
[`oscrigol.py`](../oscilloscopes/rigol-MSO2102A/oscrigol.py).

## Proposito

`oscrigol` controla un osciloscopio Rigol MSO2102A por TCP/IP usando PyVISA.
Mantiene una interfaz similar a las clases Tektronix del repositorio. La clase
incluye un modo legacy y un modo optimizado para reducir el tiempo de descarga
sin aceptar lecturas vacias o parciales.

## Conexion VISA

La clase acepta dos transportes:

- `use_socket=False`: recurso `TCPIP0::<ip>::INSTR`, usando VXI-11.
- `use_socket=True`: recurso `TCPIP0::<ip>::5555::SOCKET`, usando raw sockets.

Tambien acepta dos backends VISA con nombres legibles:

- `visa_backend="pyvisa"`: usa `pyvisa-py`.
- `visa_backend="nivisa"`: usa la biblioteca NI-VISA instalada en el sistema.

El modo socket requiere terminadores `\n` para lectura y escritura; `initComm()`
los configura automaticamente.

## Configuracion principal

La configuracion se carga con `config(...)`:

- canales: `channels=(1,)` o multiples canales;
- ancho de banda, acoplamiento, inversion e impedancia por canal;
- trigger de flanco: fuente, acoplamiento, nivel y pendiente;
- modo de descarga: `download_mode="legacy"` o `download_mode="fast"`;
- profundidad de memoria `mdepth`.

Luego se suele llamar:

1. `initComm()`
2. `setEdgeTrigger(...)`
3. `setChannel(...)`
4. `setVertScale(...)`
5. `setHorScale(...)`
6. `run()`
7. `setSampAcquisition()`
8. `setandcheckmdepth(...)`

## Descarga legacy

`getchannels(...)` en modo legacy hace:

1. `:RUN`
2. espera fija;
3. `:STOP`
4. descarga RAW con `getVertValues(...)`;
5. convierte bytes a volts usando escala y offset del canal.

Es mas simple, pero tiene esperas fijas y por eso es mas lento.

## Descarga optimizada

`getchannelsFast(...)` usa `:SINGle` y polling del estado de trigger:

1. arma el osciloscopio con `:SINGle`;
2. espera hasta que `:TRIGger:STATus?` devuelva `STOP`;
3. configura la descarga RAW;
4. espera `:WAV:STAT?`;
5. lee `:WAV:DATA?` con `query_binary_values`;
6. valida que se hayan recibido exactamente `mdepth` muestras;
7. si falla, limpia el buffer VISA y reintenta.

Parametros importantes:

- `waveform_points_timeout=0.5`: margen para evitar lecturas parciales despues de
  que el Rigol informa `IDLE`.
- `max_retries=2`: reintentos ante descargas vacias, parciales o respuestas
  desincronizadas.
- `min_vpp`: umbral opcional para rechazar capturas con amplitud demasiado baja.

La clase guarda el numero de intentos usados en `_last_acquisition_attempts`.
El benchmark lo usa para reportar `attempts` y `retries`.

## Validaciones de robustez

La clase protege varios casos observados durante las pruebas:

- respuestas ASCII corridas, como leer `STOP` donde se esperaba un numero;
- lecturas binarias vacias;
- descargas parciales, por ejemplo 1400 muestras en lugar de 70000;
- timeouts durante `:WAV:DATA?`;
- cierre VISA que falla luego de un error de comunicacion.

Ante errores de comunicacion, `_clearCommBuffer()` intenta limpiar la sesion para
evitar que bytes binarios pendientes contaminen consultas posteriores.

## Benchmark recomendado

El testbench principal esta en
[`benchmark_oscrigol_download.py`](../oscilloscopes/rigol-MSO2102A/benchmark_oscrigol_download.py)
y tambien existe en formato notebook:
[`benchmark_oscrigol_download.ipynb`](../oscilloscopes/rigol-MSO2102A/benchmark_oscrigol_download.ipynb).

Comando recomendado para hardware con NI-VISA y socket:

```bash
python oscilloscopes/rigol-MSO2102A/benchmark_oscrigol_download.py \
  --backend hardware \
  --transport socket \
  --visa-backend nivisa \
  --iterations 32
```

Comparacion contra pyvisa-py:

```bash
python oscilloscopes/rigol-MSO2102A/benchmark_oscrigol_download.py \
  --backend hardware \
  --transport socket \
  --visa-backend pyvisa \
  --iterations 32
```

El CSV resultante incluye tiempo, cantidad de muestras, Vpp, intentos,
reintentos y errores. Una descarga debe considerarse valida solo si:

- `samples_ok` es verdadero;
- `signal_ok` es verdadero;
- `error` esta vacio.

## Resultados principales

Resumen de las pruebas realizadas con `mdepth=70000`, CH1, trigger en CH1 a
100 mV y la senal de prueba indicada abajo. Los valores son orientativos porque
dependen del estado de red, backend VISA y retries.

| Transporte | Backend VISA | Metodo | Iteraciones | Mediana [s] | Promedio [s] | Resultado |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `instr` | `pyvisa` | `getchannels` | 10 | 3.426 | 3.455 | Baseline legacy |
| `instr` | `pyvisa` | `getchannelsFast` | 10 | 2.903 | 2.900 | Mejora moderada |
| `socket` | `pyvisa` | `getchannels` | 10 | 1.341 | 1.394 | Gran mejora por raw socket |
| `socket` | `pyvisa` | `getchannelsFast` | 32 | 1.273 | 1.274 | Estable y predecible |
| `socket` | `nivisa` | `getchannelsFast` | 32 | ~0.99 | ~1.07 | Mas rapido; requiere validar retries |

La mejor configuracion medida hasta ahora es `socket + nivisa +
getchannelsFast`, usando `waveform_points_timeout=0.5` y `max_retries=2`.
Aunque `pyvisa` fue algo mas lento, resulto muy estable en las corridas de
comparacion.

## Senal de prueba usada

Las pruebas actuales usan un DSS Function Generator 60 MHz MCP MPF3060 conectado
al CH1 del Rigol:

- modo senal arbitraria;
- canal B-Arb;
- forma B31 Earthquake;
- modo BURST activado;
- carrier frequency: 20 kHz;
- CHB amplitude: 1 Vpp;
- Burst N Cycles: 1 Cycle;
- duty: 50 %.

La senal debe ocupar la totalidad de la pantalla del osciloscopio para que la
comparacion de forma de onda sea significativa.

El uso actual esta enfocado en CH1, con trigger por CH1 a 100 mV, escala
vertical inicial de 50 mV/div y escala horizontal de 10 us/div.

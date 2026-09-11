# Rigol MSO2102A: clase `oscrigol`

Guia breve para entender y probar la clase
[`oscrigol.py`](../oscilloscopes/rigol-MSO2102A/oscrigol.py) y sus wrappers de
laboratorio.

## Proposito

`oscrigol` controla un osciloscopio Rigol MSO2102A por TCP/IP usando PyVISA.
Mantiene una interfaz similar a las clases Tektronix del repositorio. La clase
incluye un modo legacy y un modo optimizado para reducir el tiempo de descarga
sin aceptar lecturas vacias o parciales. El modo optimizado ya es usado por los
wrappers `oscrigol_oil.py` y `oscrigol_pacter.py`.

## Conexion VISA

La clase acepta dos transportes:

- `use_socket=False`: recurso `TCPIP0::<ip>::INSTR`, usando VXI-11.
- `use_socket=True`: recurso `TCPIP0::<ip>::5555::SOCKET`, usando raw sockets.

Tambien acepta dos backends VISA con nombres legibles:

- `visa_backend="pyvisa"`: usa `pyvisa-py`.
- `visa_backend="nivisa"`: usa la biblioteca NI-VISA instalada en el sistema.

El modo socket requiere terminadores `\n` para lectura y escritura; `initComm()`
los configura automaticamente.

El default de la clase y de los wrappers de laboratorio es `visa_backend="pyvisa"`
para facilitar reproducibilidad. Para comparar contra NI-VISA, usar
`visa_backend="nivisa"`.

## Configuracion principal

La configuracion se carga con `config(...)`:

- canales: `channels=(1,)` o multiples canales;
- ancho de banda, acoplamiento, inversion e impedancia por canal;
- trigger de flanco: fuente, acoplamiento, nivel y pendiente;
- modo de descarga: `download_mode="legacy"` o `download_mode="fast"`;
- profundidad de memoria `mdepth`.
- opciones del modo rapido: `poll_interval`, `trigger_timeout`,
  `waveform_delay`, `waveform_points_timeout`, `arm_delay`, `max_retries` y
  `min_vpp`.

Ejemplo minimo para CH1 con socket y descarga rapida:

```python
MSO2102A = oscrigol(
    "192.168.2.2",
    use_socket=True,
    visa_backend="pyvisa",
)

MSO2102A.config(
    channels=(1,),
    chanBand=("20M",),
    chanCoup=("AC",),
    chanInv=("OFF",),
    chanImp=("OMEG",),
    trigSource="CHAN1",
    trigCoup="AC",
    trigLevel=0.1,
    trigSlope="POS",
    acquisition=1,
    mdepth=70000,
    download_mode="fast",
    waveform_points_timeout=0.5,
    max_retries=2,
)
```

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
- `arm_delay=0.05`: espera corta despues de `:SINGle` antes de consultar el
  estado de trigger.

La clase guarda el numero de intentos usados en `_last_acquisition_attempts`.
El benchmark lo usa para reportar `attempts` y `retries`.

## Autoajuste vertical

`autoAdjustVertScale(...)` ajusta escala y offset vertical manteniendo la misma
logica de reescalado historica. Por defecto usa el motor interno de medicion
del Rigol (`minmax_source="measure"`), igual que la implementacion anterior.

Para comparar contra la descarga real, se puede activar:

```python
MSO2102A.autoAdjustVertScale(
    channels=(1,),
    minmax_source="raw",
    saturation_min_count=2,
)
```

Con `minmax_source="raw"` obtiene `Vmin` y `Vmax` desde una captura RAW
sincronizada:

1. re-aplica el trigger configurado con `setEdgeTrigger(...)`;
2. configura el modo de adquisicion `PEAK` o `NORM`;
3. arma una captura con `:SINGle`;
4. espera el disparo con `waitForSingleTrigger(...)`;
5. descarga la senal RAW del canal;
6. calcula minimo y maximo con NumPy;
7. marca saturacion si al menos `saturation_min_count` bytes crudos quedan
   fuera del rango seguro del ADC (`<1` o `>254`).

Esto evita depender de `:MEASure:VMAX?` y `:MEASure:VMIN?`, que el manual
asocia al motor interno de medicion y a la region de pantalla/cursor, no a una
garantia explicita de memoria RAW completa.

Si se quiere conservar el comportamiento historico:

```python
MSO2102A.autoAdjustVertScale(channels=(1,), minmax_source="measure")
```

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

El script usa nombres claros para el backend:

- `--visa-backend pyvisa`
- `--visa-backend nivisa`

El modo fake no requiere hardware y sirve para validar el testbench:

```bash
python oscilloscopes/rigol-MSO2102A/benchmark_oscrigol_download.py \
  --backend fake \
  --iterations 5 \
  --methods legacy,fast
```

## Notebooks vigentes

- [`benchmark_oscrigol_download.ipynb`](../oscilloscopes/rigol-MSO2102A/benchmark_oscrigol_download.ipynb):
  version interactiva del benchmark, con graficos de formas de onda, tiempos,
  retries y calidad de senal.
- [`manual_test_oscrigol.ipynb`](../oscilloscopes/rigol-MSO2102A/manual_test_oscrigol.ipynb):
  prueba manual de conexion, autoajuste y una captura con la clase base.
- [`med_oscrigol_oil.ipynb`](../oscilloscopes/rigol-MSO2102A/med_oscrigol_oil.ipynb):
  template generico para mediciones OIL usando `oil_med(...)`.

## Wrappers de laboratorio

`oscrigol_oil.py` y `oscrigol_pacter.py` heredan de `oscrigol`. Mantienen los
defaults y funciones historicas de cada experimento, pero delegan comunicacion,
descarga, retries y validaciones en la clase base testeada.

Ejemplo OIL:

```python
from oscrigol_oil import oil_med, plotresults

t, MV, E, T = oil_med(
    Nmed=10,
    acq=1,
    mdepth=70000,
    visa_backend="pyvisa",
    download_mode="fast",
    waveform_points_timeout=0.5,
    max_retries=2,
)
```

Ejemplo PACTER:

```python
from oscrigol_pacter import pacter_med, plotresults

t, MV, E, T = pacter_med(
    Nmed=10,
    acq=1,
    mdepth=70000,
    visa_backend="pyvisa",
    download_mode="fast",
)
```

Si estos archivos estan dentro de una carpeta `utils/`, se pueden importar como:

```python
from utils.oscrigol_oil import oil_med
from utils.oscrigol_pacter import pacter_med
```

Los wrappers tienen un fallback de importacion para encontrar `oscrigol.py` en
el mismo directorio.

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
comparacion. Para trabajo rutinario conviene priorizar que cada descarga tenga
`samples_ok=True`, `signal_ok=True` y pocos retries.

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

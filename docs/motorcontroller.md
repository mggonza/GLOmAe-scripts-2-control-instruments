# GRBL motor controller

Guia breve para entender y probar
[`motorcontroller.py`](../MotionController/MotorController/motorcontroller.py).

## Proposito

`MotorController` controla una plataforma basada en GRBL por puerto serie. El
codigo esta pensado para mediciones de laboratorio donde se necesita mover una
muestra en coordenadas logicas, aplicar limites de seguridad y recorrer puntos o
grillas.

El controlador no abre el puerto serie por si mismo: recibe un objeto
`serial.Serial` ya creado. Esto permite decidir desde el notebook o script que
puerto, baudrate y timeout usar.

## Conexion basica

```python
import serial
from MotionController.MotorController.motorcontroller import MotorController

ser = serial.Serial("/dev/ttyUSB0", baudrate=115200, timeout=2)
mc = MotorController(ser)

mc.wake_up()
mc.initialize(feed=80.0)
```

`initialize()` desbloquea GRBL con `$X`, configura unidades en milimetros con
`G21` y fija el feed inicial.

## Ejes logicos

La clase separa ejes logicos de ejes fisicos GRBL mediante `axis_map`.
El default es:

```python
{
    "x": ("X", 1),
    "y": ("Z", 1),
    "z": (None, 1),
}
```

Esto significa que el eje logico `x` mueve el eje GRBL `X`, el eje logico `y`
mueve el eje GRBL `Z`, y el eje logico `z` queda sin uso. El signo permite
invertir el sentido sin cambiar el resto del codigo:

```python
mc.set_axis_map({
    "x": ("X", 1),
    "y": ("Z", -1),
    "z": (None, 1),
})
```

## Estado persistente

La clase guarda estado local en el directorio de trabajo:

- `motor_state.json`: home logico, posicion logica, limites y estado de limites.
- `motor_history.jsonl`: historial de eventos en formato JSON lines.

La posicion es una referencia logica mantenida por el script. Si el motor se
mueve por fuera del controlador, conviene reestablecer el home logico con
`set_home()` o revisar el estado antes de continuar.

## Home logico

`set_home()` no ejecuta un homing fisico. Envia `G92` para declarar la posicion
actual como origen logico y actualiza la posicion local a `(0, 0, 0)`.

```python
mc.set_home()
mc.go_home(feed=80.0)
```

`go_home()` mueve a la posicion guardada como home mediante movimiento absoluto.

## Movimientos

Movimiento relativo:

```python
mc.move_relative(dx=0.1, dy=0.0, feed=80.0)
```

Movimiento absoluto:

```python
mc.move_absolute(x=0.5, y=-0.2, feed=80.0)
```

Ambos metodos validan limites antes de moverse, envian comandos `G1` y, por
defecto, esperan hasta que GRBL informe `Idle`.

`jog(...)` usa comandos `$J=G91 ...` para movimiento manual tipo joystick:

```python
mc.jog(dx=0.05, feed=60.0)
mc.jog_cancel()
```

## Limites logicos

Los limites evitan iniciar movimientos fuera de una ventana de trabajo definida:

```python
mc.set_limits(
    x_min=-1.0,
    x_max=1.0,
    y_min=-1.0,
    y_max=1.0,
)
mc.enable_limits()
```

Para pruebas controladas se pueden desactivar:

```python
mc.disable_limits()
```

Usar esto con cuidado: la proteccion es logica y depende de que la posicion
local represente correctamente la posicion real.

## Grillas y barridos

`scan_points(...)` ejecuta una lista explicita de puntos `(x, y)` y permite
agregar un callback por punto:

```python
def medir_punto(i, x, y):
    print(f"Punto {i}: X={x:.3f}, Y={y:.3f}")
    input("Enter para medir")
    return True

mc.scan_points(
    points=[(0.0, 0.0), (0.1, 0.0), (0.1, 0.1)],
    feed=80.0,
    on_point=medir_punto,
    wait_mode="none",
)
```

`scan_grid(...)` genera grillas regulares con patrones:

- `zigzag`: alterna el sentido de cada fila para reducir recorrido.
- `raster`: recorre filas siempre en el mismo sentido.
- `spiral`: ordena desde el centro hacia afuera.

```python
mc.scan_grid(
    rows=5,
    cols=5,
    step_x=0.1,
    step_y=0.1,
    pattern="zigzag",
    centered=True,
    on_point=medir_punto,
)
```

Tambien hay dos variantes calibradas:

- `scan_grid_calibrated(...)`: interpola a partir de cuatro esquinas medidas.
- `scan_from_calibration_grid(...)`: interpola desde una grilla de calibracion
  completa.

## Herramientas auxiliares

El directorio tambien contiene:

- `jogGRBL.py`: interfaz `curses` simple para mover X/Y/Z con teclado.
- `jogGRBL_calibration.py`: interfaz `curses` para relevar una grilla de
  calibracion y exportarla.
- `testbench_motorcontroller.ipynb`: notebook de prueba del controlador.

Estas herramientas son practicas para encontrar home, validar sentidos de ejes y
generar puntos de calibracion antes de automatizar una medicion completa.

## Recomendaciones de uso

1. Verificar puerto serie y desbloquear GRBL.
2. Confirmar sentido de ejes con movimientos chicos.
3. Definir `axis_map` si el montaje usa ejes fisicos distintos.
4. Establecer home logico con la muestra en posicion conocida.
5. Configurar limites logicos conservadores.
6. Probar una grilla chica antes de ejecutar una medicion larga.

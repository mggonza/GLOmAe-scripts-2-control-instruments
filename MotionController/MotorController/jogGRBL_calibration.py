import json
import sys
import time
import serial
import curses
from dataclasses import dataclass, asdict
from pathlib import Path

STATE_FILE = Path("motor_state.json")

# Archivos de salida para calibración
CAL_ROWS = 7
CAL_COLS = 7
CAL_POINTS_FILE = Path("calibration_points.json")
CAL_GRID_FILE = Path("calibration_grid.py")


@dataclass
class JogState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    step: float = 0.1
    feed: float = 80.0  # mm/min


def load_state() -> JogState:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return JogState(**data)
        except Exception:
            pass
    return JogState()


def save_state(st: JogState):
    STATE_FILE.write_text(json.dumps(asdict(st), indent=2), encoding="utf-8")


def load_calibration_points():
    """
    Carga puntos de calibración previamente guardados.

    El archivo JSON guarda claves como "0,0", "0,1", etc.
    Internamente se convierten a tuplas (row, col).
    """
    if CAL_POINTS_FILE.exists():
        try:
            data = json.loads(CAL_POINTS_FILE.read_text(encoding="utf-8"))
            return {
                tuple(map(int, key.split(","))): tuple(value)
                for key, value in data.items()
            }
        except Exception:
            pass
    return {}


def save_calibration_points(points):
    """
    Guarda los puntos de calibración en formato JSON.

    points[(row, col)] = (x_mm, z_mm)
    """
    data = {
        f"{r},{c}": [x, z]
        for (r, c), (x, z) in points.items()
    }

    CAL_POINTS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def export_calibration_grid_py(points):
    """
    Exporta un archivo .py listo para importar desde MotorController.

    El formato es:
        calibration_grid[(row, col)] = (x_mm, y_logico_mm)

    En este script se usan X y Z físicos.
    Por lo tanto, el segundo valor exportado corresponde al Z físico,
    que luego puede interpretarse como eje lógico y en MotorController.
    """
    lines = []
    lines.append("calibration_grid = {")

    for r in range(CAL_ROWS):
        for c in range(CAL_COLS):
            if (r, c) in points:
                x, z = points[(r, c)]
                lines.append(f"    ({r}, {c}): ({x:.3f}, {z:.3f}),")

    lines.append("}")

    CAL_GRID_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def next_calibration_index(points):
    """
    Devuelve el próximo índice de calibración en orden raster:
    izquierda a derecha, arriba hacia abajo.

    Para una grilla 7x7:
        (0,0), (0,1), ..., (0,6),
        (1,0), ..., (6,6)
    """
    n = len(points)

    if n >= CAL_ROWS * CAL_COLS:
        return None

    row = n // CAL_COLS
    col = n % CAL_COLS
    return row, col


def reset_calibration_points():
    """
    Borra los archivos de calibración existentes.
    """
    if CAL_POINTS_FILE.exists():
        CAL_POINTS_FILE.unlink()

    if CAL_GRID_FILE.exists():
        CAL_GRID_FILE.unlink()


# ==============================
# MOTOR CONTROLLER
# ==============================

class MotorController:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 2.0):
        self.ser = serial.Serial(port, baudrate=baud, timeout=timeout)
        time.sleep(2.0)  # reset Arduino
        self._wake()

    def _wake(self):
        self.ser.write(b"\r\n\r\n")
        time.sleep(0.3)
        self.ser.reset_input_buffer()

    def _readline(self) -> str:
        return self.ser.readline().decode(errors="ignore").strip()

    def send(self, line: str):
        self.ser.write((line.strip() + "\n").encode())
        self.ser.flush()

        while True:
            r = self._readline()
            if not r:
                continue

            rl = r.lower()
            if rl.startswith("ok") or rl.startswith("error"):
                break

    def status(self, timeout_s: float = 0.5) -> str:
        """
        Consulta estado GRBL y devuelve solo la línea tipo:
        <Idle|MPos:...|FS:...>
        """
        self.ser.reset_input_buffer()
        self.ser.write(b"?")
        self.ser.flush()

        t0 = time.time()

        while time.time() - t0 < timeout_s:
            line = self.ser.readline().decode(errors="ignore").strip()

            if line.startswith("<") and line.endswith(">"):
                return line

        return "status timeout"

    def init(self, feed: float):
        self.send("$X")      # unlock
        self.send("G21")     # mm
        self.send(f"F{feed:.2f}")

    def move_inc(self, dx=0.0, dy=0.0, dz=0.0, feed=80.0):
        self.send("G91")
        self.send(f"F{feed:.2f}")
        self.send(f"G1 X{dx:.3f} Y{dy:.3f} Z{dz:.3f}")

    def move_abs(self, x=0.0, y=0.0, z=0.0, feed=80.0):
        self.send("G90")
        self.send(f"F{feed:.2f}")
        self.send(f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f}")

    def set_work_zero_here(self):
        self.send("G90")
        self.send("G92 X0 Y0 Z0")


# ==============================
# INTERFAZ CURSES
# ==============================

def safe_addstr(stdscr, row, col, text):
    """
    Evita que curses rompa si la terminal es chica.
    """
    try:
        height, width = stdscr.getmaxyx()

        if row >= height:
            return

        max_len = max(0, width - col - 1)
        stdscr.addstr(row, col, str(text)[:max_len])

    except curses.error:
        pass


def ui(stdscr, controller: MotorController, st: JogState):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    info = ""
    calibration_points = load_calibration_points()

    while True:
        stdscr.erase()
        status = controller.status()

        saved_count = len(calibration_points)
        next_idx = next_calibration_index(calibration_points)

        safe_addstr(stdscr, 0, 0, "Jog GRBL Calibration - X/Z físicos")
        safe_addstr(stdscr, 1, 0, "A/D: X- / X+     F/R: Z- / Z+     W/S: Y+ / Y- (opcional)")
        safe_addstr(stdscr, 2, 0, "Steps: 1=5 mm | 2=1 mm | 3=0.5 mm | 4=0.1 mm | 5=0.05 mm | 6=0.01 mm")
        safe_addstr(stdscr, 3, 0, "+/-: feed    H: set HOME    G: go HOME")
        safe_addstr(stdscr, 4, 0, "C: guardar punto calibración 7x7 raster    U: deshacer último    X: borrar calibración")
        safe_addstr(stdscr, 5, 0, "P: guardar estado    Q: salir")

        safe_addstr(stdscr, 7, 0, "Posición física actual:")
        safe_addstr(stdscr, 8, 0, f"X={st.x:.3f} mm   Y={st.y:.3f} mm   Z={st.z:.3f} mm")
        safe_addstr(stdscr, 9, 0, f"Step={st.step:.3f} mm   Feed={st.feed:.1f} mm/min")
        safe_addstr(stdscr, 10, 0, f"GRBL: {status}")

        safe_addstr(stdscr, 12, 0, f"Puntos calibración guardados: {saved_count}/{CAL_ROWS * CAL_COLS}")

        if next_idx is not None:
            safe_addstr(stdscr, 13, 0, f"Próximo punto a guardar: {next_idx}  [orden raster: izquierda->derecha, arriba->abajo]")
        else:
            safe_addstr(stdscr, 13, 0, "Grilla de calibración completa")

        safe_addstr(stdscr, 15, 0, f"Info: {info}")

        # Mostrar pocos puntos recientes para evitar errores de pantalla.
        recent = list(calibration_points.items())[-5:]
        safe_addstr(stdscr, 17, 0, "Últimos puntos guardados:")
        for k, ((r, c), (x, z)) in enumerate(recent):
            safe_addstr(stdscr, 18 + k, 0, f"  ({r},{c}) -> ({x:.3f}, {z:.3f})")

        ch = stdscr.getch()

        if ch == -1:
            continue

        c = chr(ch).lower() if 0 <= ch < 256 else ""

        try:
            if c == "q":
                return

            # Step presets
            if c == "1":
                st.step = 5.0
                info = "Step 5 mm"

            elif c == "2":
                st.step = 1.0
                info = "Step 1 mm"

            elif c == "3":
                st.step = 0.5
                info = "Step 0.5 mm"

            elif c == "4":
                st.step = 0.1
                info = "Step 0.1 mm"

            elif c == "5":
                st.step = 0.05
                info = "Step 0.05 mm"

            elif c == "6":
                st.step = 0.01
                info = "Step 0.01 mm"

            # Feed
            elif c == "+" or ch == ord("="):
                st.feed += 10
                info = f"Feed {st.feed:.1f}"

            elif c == "-":
                st.feed = max(1, st.feed - 10)
                info = f"Feed {st.feed:.1f}"

            # Homing lógico
            elif c == "h":
                controller.set_work_zero_here()
                st.x = st.y = st.z = 0.0
                save_state(st)
                info = "HOME seteado (G92 X0 Y0 Z0)"

            elif c == "g":
                controller.move_abs(0.0, 0.0, 0.0, st.feed)
                st.x = st.y = st.z = 0.0
                save_state(st)
                info = "Ir a HOME"

            elif c == "p":
                save_state(st)
                save_calibration_points(calibration_points)
                export_calibration_grid_py(calibration_points)
                info = "Estado y calibración guardados"

            # Guardar punto de calibración automáticamente
            elif c == "c":
                idx = next_calibration_index(calibration_points)

                if idx is None:
                    info = "Grilla 7x7 completa. No se guardan más puntos."
                else:
                    r, col = idx

                    # Se guardan X y Z físicos como coordenadas de calibración.
                    # El Z físico será usado como eje lógico y en MotorController.
                    calibration_points[(r, col)] = (
                        round(st.x, 3),
                        round(st.z, 3)
                    )

                    save_calibration_points(calibration_points)
                    export_calibration_grid_py(calibration_points)

                    info = f"Punto ({r},{col}) guardado: X={st.x:.3f}, Z={st.z:.3f}"

            # Deshacer último punto guardado
            elif c == "u":
                if calibration_points:
                    last_idx = sorted(calibration_points.keys())[-1]
                    calibration_points.pop(last_idx)
                    save_calibration_points(calibration_points)
                    export_calibration_grid_py(calibration_points)
                    info = f"Último punto eliminado: {last_idx}"
                else:
                    info = "No hay puntos para eliminar"

            # Borrar calibración
            elif c == "x":
                calibration_points.clear()
                reset_calibration_points()
                info = "Calibración borrada"

            # Jog físico
            elif c in ("w", "a", "s", "d", "r", "f"):
                dx = dy = dz = 0.0

                if c == "w":
                    dy = +st.step
                if c == "s":
                    dy = -st.step
                if c == "d":
                    dx = +st.step
                if c == "a":
                    dx = -st.step
                if c == "r":
                    dz = +st.step
                if c == "f":
                    dz = -st.step

                controller.move_inc(dx, dy, dz, st.feed)

                st.x = round(st.x + dx, 3)
                st.y = round(st.y + dy, 3)
                st.z = round(st.z + dz, 3)

                save_state(st)

                info = f"dX={dx:+.3f} dY={dy:+.3f} dZ={dz:+.3f}"

        except Exception as e:
            info = f"ERROR: {e}"


def main():
    PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"

    st = load_state()
    controller = MotorController(PORT)
    controller.init(st.feed)

    curses.wrapper(ui, controller, st)

    save_state(st)


if __name__ == "__main__":
    main()

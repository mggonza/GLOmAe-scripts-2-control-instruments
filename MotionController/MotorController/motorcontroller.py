from pathlib import Path
import json
import time
from datetime import datetime
from typing import Callable, Optional, Union
import serial

class MotorController:
    """
    Controlador de motores basado en GRBL por puerto serie.

    Modos principales:
    - move_relative / move_absolute: movimientos determinísticos con G1.
    - jog / jog_cancel: movimiento manual tipo joystick usando $J=.

    Incluye home lógico, persistencia de posición, historial de eventos,
    límites lógicos y barridos en grilla.
    """

    STATE_FILE = Path("motor_state.json")
    HISTORY_FILE = Path("motor_history.jsonl")

    def __init__(self, ser: serial.Serial, axis_map: Optional[dict] = None):

        # Puerto serie ya inicializado y abierto
        # (ej: serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT))
        self.ser = ser

        # Ejes lógicos -> ejes físicos GRBL
        # Por defecto, mapea x->X, y->Z, z no se usa.
        # Inversion de dirección por signo:
        #    1 para normal,
        #   -1 para invertir sentido.
        self.axis_map = axis_map or {
            "x": ("X", 1),  # eje lógico x -> eje GRBL X
            "y": ("Z", 1),   # eje lógico y -> eje GRBL Z
            "z": (None, 1),  # eje lógico z no se usa por ahora
        }

        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.home = {"x": 0.0, "y": 0.0, "z": 0.0}

        self.limits = {
            "x_min": -0.5,
            "x_max":  0.5,
            "y_min": -0.5,
            "y_max":  0.5,
            "z_min": -0.2,
            "z_max":  0.2,
        }
        self.limits_enabled = True

        self.load_state()

    def _axis(self, logical_axis: str, value: float) -> str | None:
        real_axis = self.axis_map.get(logical_axis)

        if real_axis is None:
            return None

        return f"{real_axis}{value:.4f}"

    def set_axis_map(self, axis_map: dict):
        self.axis_map = axis_map

    def _now(self):
        return datetime.now().isoformat(timespec="seconds") + "Z"

    def _readline(self):
        return self.ser.readline().decode(errors="ignore").strip()

    def _log_event(self, event: str, **data):
        row = {"ts": self._now(), "event": event, **data}
        with self.HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def save_state(self):
        data = {
            "home": self.home,
            "position": self.position,
            "limits": self.limits,
            "limits_enabled": self.limits_enabled,
            "updated_at": self._now(),
        }
        self.STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_state(self):
        if not self.STATE_FILE.exists():
            return
        try:
            data = json.loads(self.STATE_FILE.read_text(encoding="utf-8"))
            self.home = data.get("home", self.home)
            self.position = data.get("position", self.position)
            self.limits = data.get("limits", self.limits)
            self.limits_enabled = data.get("limits_enabled", self.limits_enabled)
        except Exception:
            pass

    def send(self, cmd: str):
        """Envía un comando estándar y espera ok/error."""
        self.ser.write((cmd.strip() + "\n").encode())
        self.ser.flush()
        while True:
            r = self._readline()
            if not r:
                continue
            rl = r.lower()
            if rl.startswith("ok") or rl.startswith("error"):
                return r

    def wake_up(self, wait_s: float = 2.0) -> None:
        self.ser.write(b"\r\n\r\n")
        self.ser.flush()
        time.sleep(wait_s)
        self.ser.reset_input_buffer()

    def status(self, timeout_s: float = 1.0) -> str:
        """
        Consulta el estado actual de GRBL usando '?'.
        Devuelve la línea de estado tipo:
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

        raise TimeoutError("No se recibió estado GRBL válido.")



    def initialize(self, feed: float = 80.0):
        self.send("$X")
        self.send("G21")
        self.send(f"F{feed:.2f}")
        self._log_event("initialize", feed=feed)

    def set_limits(self, x_min=None, x_max=None, y_min=None, y_max=None, z_min=None, z_max=None):
        updates = {
            "x_min": x_min, "x_max": x_max,
            "y_min": y_min, "y_max": y_max,
            "z_min": z_min, "z_max": z_max,
        }
        for key, value in updates.items():
            if value is not None:
                self.limits[key] = float(value)
        self._validate_limits_definition()
        self.save_state()
        self._log_event("set_limits", **self.limits)

    def enable_limits(self):
        self.limits_enabled = True
        self.save_state()
        self._log_event("enable_limits")

    def disable_limits(self):
        self.limits_enabled = False
        self.save_state()
        self._log_event("disable_limits")

    def _validate_limits_definition(self):
        if self.limits["x_min"] >= self.limits["x_max"]:
            raise ValueError("Límites inválidos: x_min debe ser menor que x_max")
        if self.limits["y_min"] >= self.limits["y_max"]:
            raise ValueError("Límites inválidos: y_min debe ser menor que y_max")
        if self.limits["z_min"] >= self.limits["z_max"]:
            raise ValueError("Límites inválidos: z_min debe ser menor que z_max")

    def _check_limits(self, x: float, y: float, z: float):
        if not self.limits_enabled:
            return
        errors = []
        if not (self.limits["x_min"] <= x <= self.limits["x_max"]):
            errors.append(f"X={x:.4f} mm fuera de rango [{self.limits['x_min']:.4f}, {self.limits['x_max']:.4f}]")
        if not (self.limits["y_min"] <= y <= self.limits["y_max"]):
            errors.append(f"Y={y:.4f} mm fuera de rango [{self.limits['y_min']:.4f}, {self.limits['y_max']:.4f}]")
        if not (self.limits["z_min"] <= z <= self.limits["z_max"]):
            errors.append(f"Z={z:.4f} mm fuera de rango [{self.limits['z_min']:.4f}, {self.limits['z_max']:.4f}]")
        if errors:
            message = "ALERTA: movimiento fuera de límites operativos. " + " | ".join(errors)
            self._log_event("limit_exceeded", requested_x=x, requested_y=y, requested_z=z, message=message, **self.limits)
            raise ValueError(message)

    def set_home(self):
        # Set home lógico en la posición actual.
        # No mueve el motor, solo redefine el origen de coordenadas.
        cmd = "G92"
        if self.axis_map["x"][0] is not None:
            axis, _ = self.axis_map["x"]
            cmd += f" {axis}0"

        if self.axis_map["y"][0] is not None:
            axis, _ = self.axis_map["y"]
            cmd += f" {axis}0"

        if self.axis_map["z"][0] is not None:
            axis, _ = self.axis_map["z"]
            cmd += f" {axis}0"

        response = self.send(cmd)

        # Actualiza posición y home lógicos a (0,0,0) en coordenadas del mundo real.
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.home = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.save_state()
        self._log_event("set_home", x=0.0, y=0.0, z=0.0)

        return response

    def go_home(self, feed: float = 80.0):
        return self.move_absolute(x=self.home["x"], y=self.home["y"], z=self.home["z"], feed=feed)

    def wait_until_idle(self, timeout_s: float = 30.0, poll_s: float = 0.05):
        t0 = time.time()

        while True:
            st = self.status()
            if "Idle" in st:
                return st
            if time.time() - t0 > timeout_s:
                raise TimeoutError(f"Timeout esperando Idle. Último estado: {st}")
            time.sleep(poll_s)

    def move_relative(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, feed: float = 80.0, wait_idle: bool = True) -> str:
        self.send("G91") # Modo relativo
        self.send(f"F{feed:.2f}")

        target_x = self.position["x"] + dx
        target_y = self.position["y"] + dy
        target_z = self.position["z"] + dz
        self._check_limits(target_x, target_y, target_z)

        cmd = "G1"
        if dx != 0.0 and self.axis_map["x"][0] is not None:
            axis, sign = self.axis_map["x"]
            cmd += f" {axis}{sign * dx:.4f}"

        if dy != 0.0 and self.axis_map["y"][0] is not None:
            axis, sign = self.axis_map["y"]
            cmd += f" {axis}{sign * dy:.4f}"

        if dz != 0.0 and self.axis_map["z"][0] is not None:
            axis, sign = self.axis_map["z"]
            cmd += f" {axis}{sign * dz:.4f}"

        response = self.send(cmd)
        if wait_idle:
            self.wait_until_idle()

        self.position["x"] = target_x
        self.position["y"] = target_y
        self.position["z"] = target_z

        self.save_state()
        self._log_event("move_relative", dx=dx, dy=dy, dz=dz, feed=feed, **self.position)

        return response



    def move_absolute(self, x=None, y=None, z=None, feed: float = 80.0, wait_idle: bool = True) -> str:
        self.send("G90") # Modo absoluto
        self.send(f"F{feed:.2f}")

        tx = self.position["x"] if x is None else x
        ty = self.position["y"] if y is None else y
        tz = self.position["z"] if z is None else z

        self._check_limits(tx, ty, tz)

        cmd = "G1"
        if self.axis_map["x"][0] is not None:
            axis, sign = self.axis_map["x"]
            cmd += f" {axis}{sign * tx:.4f}"

        if self.axis_map["y"][0] is not None:
            axis, sign = self.axis_map["y"]
            cmd += f" {axis}{sign * ty:.4f}"

        if self.axis_map["z"][0] is not None:
            axis, sign = self.axis_map["z"]
            cmd += f" {axis}{sign * tz:.4f}"

        response = self.send(cmd)

        if wait_idle:
            self.wait_until_idle()

        self.position["x"] = tx
        self.position["y"] = ty
        self.position["z"] = tz

        self.save_state()
        self._log_event("move_absolute", x=tx, y=ty, z=tz, feed=feed)

        return response

    def jog(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, feed: float = 80.0):
        target_x = self.position["x"] + dx
        target_y = self.position["y"] + dy
        target_z = self.position["z"] + dz
        self._check_limits(target_x, target_y, target_z)

        cmd = "$J=G91"
        if dx != 0.0 and self.axis_map["x"][0] is not None:
            axis, sign = self.axis_map["x"]
            cmd += f" {axis}{sign * dx:.4f}"

        if dy != 0.0 and self.axis_map["y"][0] is not None:
            axis, sign = self.axis_map["y"]
            cmd += f" {axis}{sign * dy:.4f}"

        if dz != 0.0 and self.axis_map["z"][0] is not None:
            axis, sign = self.axis_map["z"]
            cmd += f" {axis}{sign * dz:.4f}"

        cmd += f" F{feed:.2f}"

        response = self.send(cmd)

        self.position["x"] = target_x
        self.position["y"] = target_y
        self.position["z"] = target_z
        self.save_state()
        self._log_event("jog", dx=dx, dy=dy, dz=dz, feed=feed, **self.position)

        return response

    def jog_cancel(self):
        self.ser.write(b"\x85") # Ctrl+U cancela el movimiento de jogging en GRBL
        self.ser.flush()
        self._log_event("jog_cancel")

    def _generate_grid_points(
                                self,
                                rows: int, cols: int,
                                step_x: float, step_y: float,
                                drift_xy: float = 0.0, drift_yx: float = 0.0,
                                pattern: str = "zigzag", centered: bool = False
                            ):
        if rows < 1 or cols < 1:
            raise ValueError("rows y cols deben ser >= 1")

        if step_x <= 0:
            raise ValueError("step_x debe ser > 0")

        if step_y <= 0:
            raise ValueError("step_y debe ser > 0")

        x0 = -((cols - 1) * step_x) / 2.0 if centered else 0.0
        y0 = -((rows - 1) * step_y) / 2.0 if centered else 0.0

        if pattern == "raster":
            pts = []

            for r in range(rows):
                for c in range(cols):
                    x_base = x0 + c * step_x
                    y_base = y0 + r * step_y

                    x = round(x_base + drift_xy * y_base, 3)
                    y = round(y_base + drift_yx * x_base, 3)

                    pts.append((x, y))

            return pts

        if pattern == "zigzag":
            pts = []

            for r in range(rows):
                cols_iter = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)

                for c in cols_iter:
                    x_base = x0 + c * step_x
                    y_base = y0 + r * step_y

                    x = round(x_base + drift_xy * y_base, 3)
                    y = round(y_base + drift_yx * x_base, 3)

                    pts.append((x, y))

            return pts

        if pattern == "spiral":
            # Recorre primero los puntos más cercanos al centro.
            grid = [(r, c) for r in range(rows) for c in range(cols)]

            center_r = (rows - 1) / 2.0
            center_c = (cols - 1) / 2.0

            grid.sort(
                key=lambda rc: (rc[0] - center_r) ** 2 + (rc[1] - center_c) ** 2
            )

            pts = []

            for r, c in grid:
                x_base = x0 + c * step_x
                y_base = y0 + r * step_y

                x = round(x_base + drift_xy * y_base, 3)
                y = round(y_base + drift_yx * x_base, 3)

                pts.append((x, y))

            return pts

        raise ValueError(f"Patrón no soportado: {pattern}")

    def scan_points(
        self,
        points,
        feed: float = 80.0,
        reverse: bool = False,
        wait_mode: str = "none",
        delay_s: float = 0.0,
        on_point=None,
        on_fail: str = "retry",
        return_home: bool = False,
    ):
        """
        Ejecuta una lista de puntos lógicos (x, y).

        Esta función centraliza la lógica de movimiento, callbacks,
        manejo de fallos, validación de límites y retorno a home.

        points:
            Lista de tuplas [(x, y), ...] en coordenadas lógicas.
        """

        if reverse:
            points = list(reversed(points))

        # Validación preventiva: evita iniciar si algún punto excede límites.
        for x, y in points:
            self._check_limits(x, y, self.position["z"])

        self._log_event(
            "scan_points_start",
            n_points=len(points),
            feed=feed,
            reverse=reverse,
            wait_mode=wait_mode,
            delay_s=delay_s,
            on_fail=on_fail,
        )

        i = 0

        try:
            while i < len(points):
                x, y = points[i]

                self.move_absolute(
                    x=x,
                    y=y,
                    z=self.position["z"],
                    feed=feed,
                    wait_idle=True,
                )

                self._log_event(
                    "scan_point",
                    index=i,
                    x=x,
                    y=y,
                    z=self.position["z"],
                )

                point_ok = True
                result = None

                if on_point is not None:
                    result = on_point(i, x, y)

                    if isinstance(result, bool):
                        point_ok = result
                    elif isinstance(result, dict):
                        point_ok = bool(result.get("ok", True))

                if point_ok:
                    if wait_mode == "delay" and delay_s > 0:
                        time.sleep(delay_s)

                    elif wait_mode == "user":
                        input(
                            f"Punto {i} listo en ({x:.3f}, {y:.3f}). "
                            "Enter para continuar..."
                        )

                    i += 1
                    continue

                self._log_event(
                    "scan_point_failed",
                    index=i,
                    x=x,
                    y=y,
                    z=self.position["z"],
                    result=result,
                )

                action = on_fail

                if isinstance(result, dict) and "action" in result:
                    action = result["action"]

                if action == "retry":
                    continue

                if action == "skip":
                    i += 1
                    continue

                if action == "abort":
                    self._log_event(
                        "scan_points_abort",
                        index=i,
                        x=x,
                        y=y,
                        z=self.position["z"],
                        result=result,
                    )
                    break

                if action == "wait_user":
                    user = input(
                        f"Fallo en punto {i} ({x:.3f}, {y:.3f}). "
                        "[c] continuar, [r] reintentar, [s] saltear, [a] abortar: "
                    ).strip().lower()

                    if user == "r":
                        continue

                    if user == "s":
                        i += 1
                        continue

                    if user == "a":
                        self._log_event(
                            "scan_points_abort_user",
                            index=i,
                            x=x,
                            y=y,
                            z=self.position["z"],
                        )
                        break

                    i += 1
                    continue

                raise ValueError(f"Acción on_fail no soportada: {action}")

        finally:
            if return_home:
                self.go_home(feed=feed)

            self._log_event("scan_points_end")

    def scan_grid(self,
                  rows: int, cols: int,
                  step_x: float = 0.1, step_y: float = 0.1, step_z: float = 0.0,
                  drift_xy: float = 0.0, drift_yx: float = 0.0,
                  feed: float = 80.0,
                  pattern: str = "zigzag", centered: bool = False, reverse: bool = False,
                  wait_mode: str = "none", delay_s: float = 0.0,
                  on_point: Optional[Callable[[int, float, float], Union[bool, dict]]] = None,
                  on_fail: str = "retry",
                  return_home: bool = False
                  ):

        points = self._generate_grid_points(rows=rows, cols=cols,
                                            step_x=step_x, step_y=step_y,
                                            drift_xy=drift_xy, drift_yx=drift_yx,
                                            pattern=pattern, centered=centered)
        if reverse:
            points = list(reversed(points))

        # Validación preventiva: evita iniciar una grilla que excede límites.
        for x, y in points:
            self._check_limits(x, y, self.position["z"])

        self._log_event("scan_grid_start", rows=rows, cols=cols,
                        step_x=step_x, step_y=step_y, step_z=step_z,
                        drift_xy=drift_xy, drift_yx=drift_yx, feed=feed,
                        pattern=pattern, centered=centered, reverse=reverse,
                        wait_mode=wait_mode, delay_s=delay_s, on_fail=on_fail)

        try:
            points = self._generate_grid_points(
                rows=rows,
                cols=cols,
                step_x=step_x,
                step_y=step_y,
                drift_xy=drift_xy,
                drift_yx=drift_yx,
                pattern=pattern,
                centered=centered,
            )

            self._log_event(
                "scan_grid_start",
                rows=rows,
                cols=cols,
                step_x=step_x,
                step_y=step_y,
                step_z=step_z,
                drift_xy=drift_xy,
                drift_yx=drift_yx,
                feed=feed,
                pattern=pattern,
                centered=centered,
                reverse=reverse,
                wait_mode=wait_mode,
                delay_s=delay_s,
                on_fail=on_fail,
            )

            return self.scan_points(
                points=points,
                feed=feed,
                reverse=reverse,
                wait_mode=wait_mode,
                delay_s=delay_s,
                on_point=on_point,
                on_fail=on_fail,
                return_home=return_home,
            )

        finally:
            if return_home:
                self.go_home(feed=feed)
            self._log_event("scan_grid_end")

    def scan_grid_calibrated(
        self,
        rows: int,
        cols: int,
        top_left: tuple[float, float],
        top_right: tuple[float, float],
        bottom_left: tuple[float, float],
        bottom_right: tuple[float, float],
        feed: float = 80.0,
        pattern: str = "zigzag",
        reverse: bool = False,
        wait_mode: str = "none",
        delay_s: float = 0.0,
        on_point=None,
        on_fail: str = "retry",
        return_home: bool = False,
    ):
        """
        Wrapper de scan_points() que genera una grilla calibrada a partir
        de cuatro esquinas medidas.

        Las esquinas deben estar expresadas como posiciones lógicas absolutas
        respecto del home/origen de medición.

        Esta estrategia fuerza que:
        - primera esquina superior coincida con top_left
        - última esquina superior coincida con top_right
        - primera esquina inferior coincida con bottom_left
        - última esquina inferior coincida con bottom_right
        """

        if rows < 2 or cols < 2:
            raise ValueError("rows y cols deben ser >= 2 para usar cuatro esquinas")

        if pattern not in ("raster", "zigzag"):
            raise ValueError("pattern debe ser 'raster' o 'zigzag'")

        points = []

        for r in range(rows):
            v = r / (rows - 1)
            row_points = []

            for c in range(cols):
                u = c / (cols - 1)

                # Interpolación bilineal entre las cuatro esquinas.
                x = (
                    (1 - u) * (1 - v) * top_left[0]
                    + u * (1 - v) * top_right[0]
                    + (1 - u) * v * bottom_left[0]
                    + u * v * bottom_right[0]
                )

                y = (
                    (1 - u) * (1 - v) * top_left[1]
                    + u * (1 - v) * top_right[1]
                    + (1 - u) * v * bottom_left[1]
                    + u * v * bottom_right[1]
                )

                row_points.append((round(x, 3), round(y, 3)))

            if pattern == "zigzag" and r % 2 == 1:
                row_points.reverse()

            points.extend(row_points)

        self._log_event(
            "scan_grid_calibrated_start",
            rows=rows,
            cols=cols,
            top_left=top_left,
            top_right=top_right,
            bottom_left=bottom_left,
            bottom_right=bottom_right,
            feed=feed,
            pattern=pattern,
            reverse=reverse,
            wait_mode=wait_mode,
            delay_s=delay_s,
            on_fail=on_fail,
        )

        return self.scan_points(
            points=points,
            feed=feed,
            reverse=reverse,
            wait_mode=wait_mode,
            delay_s=delay_s,
            on_point=on_point,
            on_fail=on_fail,
            return_home=return_home,
        )


    def _generate_points_from_calibration_grid(
        self,
        calibration_grid: dict,
        cal_rows: int,
        cal_cols: int,
        rows: int,
        cols: int,
        pattern: str = "zigzag",
    ):
        """
        Genera puntos interpolados a partir de una grilla de calibración medida.

        calibration_grid:
            Diccionario con claves (r, c) y valores (x, y), usando índices base 0.

            Ejemplo para calibración 3x3:
            {
                (0, 0): (8.3, 10.5),
                (0, 1): (0.4, 10.5),
                (0, 2): (-7.1, 10.5),
                ...
            }

        cal_rows, cal_cols:
            Tamaño de la grilla de calibración medida.

        rows, cols:
            Tamaño de la grilla final deseada.

        pattern:
            'raster' o 'zigzag'.
        """

        if rows < 1 or cols < 1:
            raise ValueError("rows y cols deben ser >= 1")

        if cal_rows < 2 or cal_cols < 2:
            raise ValueError("La grilla de calibración debe tener al menos 2x2 puntos")

        if pattern not in ("raster", "zigzag"):
            raise ValueError("pattern debe ser 'raster' o 'zigzag'")

        # Verifica que la grilla de calibración esté completa.
        for r in range(cal_rows):
            for c in range(cal_cols):
                if (r, c) not in calibration_grid:
                    raise ValueError(f"Falta punto de calibración {(r, c)}")

        points = []

        for r in range(rows):
            # Coordenada vertical continua dentro de la grilla calibrada.
            v_global = r * (cal_rows - 1) / (rows - 1) if rows > 1 else 0.0

            r0 = int(v_global)
            r1 = min(r0 + 1, cal_rows - 1)
            v = v_global - r0

            row_points = []

            for c in range(cols):
                # Coordenada horizontal continua dentro de la grilla calibrada.
                u_global = c * (cal_cols - 1) / (cols - 1) if cols > 1 else 0.0

                c0 = int(u_global)
                c1 = min(c0 + 1, cal_cols - 1)
                u = u_global - c0

                p00 = calibration_grid[(r0, c0)]
                p01 = calibration_grid[(r0, c1)]
                p10 = calibration_grid[(r1, c0)]
                p11 = calibration_grid[(r1, c1)]

                # Interpolación bilineal local dentro de cada celda.
                x = (
                    (1 - u) * (1 - v) * p00[0]
                    + u * (1 - v) * p01[0]
                    + (1 - u) * v * p10[0]
                    + u * v * p11[0]
                )

                y = (
                    (1 - u) * (1 - v) * p00[1]
                    + u * (1 - v) * p01[1]
                    + (1 - u) * v * p10[1]
                    + u * v * p11[1]
                )

                row_points.append((round(x, 3), round(y, 3)))

            if pattern == "zigzag" and r % 2 == 1:
                row_points.reverse()

            points.extend(row_points)

        return points

    def scan_from_calibration_grid(
        self,
        calibration_grid: dict,
        cal_rows: int,
        cal_cols: int,
        rows: int,
        cols: int,
        feed: float = 80.0,
        pattern: str = "zigzag",
        reverse: bool = False,
        wait_mode: str = "none",
        delay_s: float = 0.0,
        on_point=None,
        on_fail: str = "retry",
        return_home: bool = False,
    ):
        """
        Wrapper de scan_points() que genera una grilla interpolada a partir
        de una grilla de calibración medida completa.

        Si rows/cols coinciden con cal_rows/cal_cols, los puntos generados
        coinciden con los puntos medidos.
        """

        points = self._generate_points_from_calibration_grid(
            calibration_grid=calibration_grid,
            cal_rows=cal_rows,
            cal_cols=cal_cols,
            rows=rows,
            cols=cols,
            pattern=pattern,
        )

        self._log_event(
            "scan_from_calibration_grid_start",
            cal_rows=cal_rows,
            cal_cols=cal_cols,
            rows=rows,
            cols=cols,
            feed=feed,
            pattern=pattern,
            reverse=reverse,
            wait_mode=wait_mode,
            delay_s=delay_s,
            on_fail=on_fail,
        )

        return self.scan_points(
            points=points,
            feed=feed,
            reverse=reverse,
            wait_mode=wait_mode,
            delay_s=delay_s,
            on_point=on_point,
            on_fail=on_fail,
            return_home=return_home,
        )

import json
import time
import serial
import curses
from dataclasses import dataclass, asdict
from pathlib import Path

STATE_FILE = Path("motor_state.json")

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

    def status(self) -> str:
        self.ser.write(b"?")
        self.ser.flush()
        return self._readline()

    def init(self, feed: float):
        self.send("$X")      # unlock
        self.send("G21")     # mm
        self.send(f"F{feed:.2f}")

    def move_inc(self, dx=0.0, dy=0.0, dz=0.0, feed=80.0):
        self.send("G91")
        self.send(f"F{feed:.2f}")
        self.send(f"G1 X{dx:.4f} Y{dy:.4f} Z{dz:.4f}")

    def move_abs(self, x=0.0, y=0.0, z=0.0, feed=80.0):
        self.send("G90")
        self.send(f"F{feed:.2f}")
        self.send(f"G1 X{x:.4f} Y{y:.4f} Z{z:.4f}")

    def set_work_zero_here(self):
        self.send("G90")
        self.send("G92 X0 Y0 Z0")

# ==============================
# INTERFAZ CURSES
# ==============================

def ui(stdscr, controller: MotorController, st: JogState):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    info = ""

    while True:
        stdscr.erase()
        status = controller.status()

        stdscr.addstr(0, 0, "MotorController - GRBL 1.1 (X/Y/Z)")
        stdscr.addstr(1, 0, "W/S: Y+/-   A/D: X- /+   R/F: Z+/-")
        stdscr.addstr(2, 0, "1/2/3: step 0.1 / 0.01 / 0.001 mm")
        stdscr.addstr(3, 0, "+/-: feed    H: set HOME   G: go HOME")
        stdscr.addstr(4, 0, "P: save state   Q: quit")

        stdscr.addstr(6, 0, f"Posición lógica:")
        stdscr.addstr(7, 0, f"X={st.x:.4f}  Y={st.y:.4f}  Z={st.z:.4f}")
        stdscr.addstr(8, 0, f"Step={st.step:.4f} mm   Feed={st.feed:.1f} mm/min")
        stdscr.addstr(9, 0, f"GRBL: {status}")
        stdscr.addstr(11, 0, f"Info: {info}")

        ch = stdscr.getch()
        if ch == -1:
            continue

        c = chr(ch).lower() if 0 <= ch < 256 else ""

        try:
            if c == "q":
                return

            # Step presets
            if c == "1":
                st.step = 0.1
                info = "Step 0.1 mm"
            elif c == "2":
                st.step = 0.01
                info = "Step 0.01 mm"
            elif c == "3":
                st.step = 0.001
                info = "Step 0.001 mm"

            # Feed
            elif c == "+" or ch == ord("="):
                st.feed += 10
                info = f"Feed {st.feed}"
            elif c == "-":
                st.feed = max(1, st.feed - 10)
                info = f"Feed {st.feed}"

            # Homing lógico
            elif c == "h":
                controller.set_work_zero_here()
                st.x = st.y = st.z = 0.0
                info = "HOME seteado (G92 X0 Y0 Z0)"

            elif c == "g":
                controller.move_abs(0.0, 0.0, 0.0, st.feed)
                st.x = st.y = st.z = 0.0
                info = "Ir a HOME"

            elif c == "p":
                save_state(st)
                info = "Estado guardado"

            # Jog XY
            elif c in ("w", "a", "s", "d", "r", "f"):
                dx = dy = dz = 0.0
                if c == "w": dy = +st.step
                if c == "s": dy = -st.step
                if c == "d": dx = +st.step
                if c == "a": dx = -st.step
                if c == "r": dz = +st.step
                if c == "f": dz = -st.step

                controller.move_inc(dx, dy, dz, st.feed)
                st.x += dx
                st.y += dy
                st.z += dz
                info = f"dX={dx:+.4f} dY={dy:+.4f} dZ={dz:+.4f}"

        except Exception as e:
            info = f"ERROR: {e}"

def main():
    PORT = "/dev/ttyUSB0"  # Cambiar según sistema
    st = load_state()
    controller = MotorController(PORT)
    controller.init(st.feed)
    curses.wrapper(ui, controller, st)
    save_state(st)

if __name__ == "__main__":
    main()

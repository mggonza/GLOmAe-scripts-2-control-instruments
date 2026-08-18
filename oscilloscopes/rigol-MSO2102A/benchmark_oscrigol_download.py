#!/usr/bin/env python3
"""
Benchmark legacy vs optimized waveform download paths for oscrigol.

Test signal used during this optimization round
------------------------------------------------
The CH1 input of the Rigol MSO2102A is driven from a DDS Function Generator
60 MHz MCP MPF3060. The generator is configured in arbitrary signal mode,
channel B-Arb, waveform B31 Earthquake, with BURST enabled:

    Carrier Frequency: 20 kHz
    CHB Amplitude: 1 Vpp
    Burst N Cycles: 1 Cycle
    Duty: 50 %

The oscilloscope is configured to display the full test signal on screen.

Examples
--------
Fake benchmark, useful to validate the testbench itself:
    python benchmark_oscrigol_download.py --backend fake --iterations 5

Hardware benchmark using the current VXI-11/INSTR path:
    python benchmark_oscrigol_download.py --backend hardware --transport instr \
        --iterations 20 --mdepth 70000

Hardware benchmark using Rigol raw sockets on port 5555:
    python benchmark_oscrigol_download.py --backend hardware --transport socket \
        --iterations 20 --mdepth 70000
"""

import argparse
import csv
import importlib.util
import statistics
import time
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
OSCRIGOL_PATH = HERE / "oscrigol.py"


def visa_backend_value(name):
    if name == "nivisa":
        return "nivisa"
    if name == "pyvisa":
        return "pyvisa"
    raise ValueError("visa backend must be 'pyvisa' or 'nivisa'")


def load_oscrigol_class():
    spec = importlib.util.spec_from_file_location("oscrigol_module", OSCRIGOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.oscrigol


class FakeRigolResource:
    def __init__(
        self,
        mdepth=70000,
        command_latency=0.015,
        binary_latency=0.08,
        trigger_polls=4,
    ):
        self.mdepth = int(mdepth)
        self.command_latency = float(command_latency)
        self.binary_latency = float(binary_latency)
        self.trigger_polls = int(trigger_polls)
        self._poll_count = 0
        self._waveform_start = 1
        self._waveform_stop = self.mdepth
        self.timeout = 5000
        self.read_termination = None
        self.write_termination = None

    def _delay(self, seconds):
        time.sleep(seconds)

    def write(self, command):
        self._delay(self.command_latency)
        command = command.strip().upper()
        if command == ":SINGLE":
            self._poll_count = 0
        elif command.startswith(":WAV:STAR "):
            self._waveform_start = int(command.split()[-1])
        elif command.startswith(":WAV:STOP "):
            self._waveform_stop = int(command.split()[-1])

    def query(self, command):
        self._delay(self.command_latency)
        command = command.strip().upper()
        if command == ":TRIGGER:STATUS?":
            self._poll_count += 1
            return "STOP\n" if self._poll_count >= self.trigger_polls else "WAIT\n"
        if command == ":WAV:STAT?":
            return f"IDLE,{self.mdepth}\n"
        if command == ":ACQ:MDEP?":
            return f"{self.mdepth}\n"
        if command == ":MEASURE:VMAX? CHANNEL2":
            return "0.125\n"
        if command.endswith(":SCAL?"):
            return "0.02\n"
        if command.endswith(":OFFS?"):
            return "0.0\n"
        if command == ":TIMEBASE:SCALE?":
            return "1e-5\n"
        if command == ":TIMEBASE:OFFSET?":
            return "0.0\n"
        if command == ":ACQUIRE:SRATE?":
            return "1e9\n"
        return "0\n"

    def query_binary_values(self, command, datatype="B", container=np.array,
                            chunk_size=None, expect_termination=None,
                            data_points=None):
        self._delay(self.binary_latency)
        n_points = self._waveform_stop - self._waveform_start + 1
        if data_points is not None:
            n_points = int(data_points)
        phase = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
        data = np.asarray(127 + 20 * np.sin(phase), dtype=np.uint8)
        return container(data)

    def close(self):
        pass


def build_scope(args, mode):
    OscRigol = load_oscrigol_class()
    scope = OscRigol(
        ip_address=args.ip,
        use_socket=args.transport == "socket",
        socket_port=args.socket_port,
        visa_backend=visa_backend_value(args.visa_backend),
    )
    scope.config(
        channels=args.channels,
        chanBand=tuple([args.bandwidth] * len(args.channels)),
        chanCoup=args.coupling,
        chanInv=tuple(["OFF"] * len(args.channels)),
        chanImp=args.impedance,
        trigSource=args.trigger_source,
        trigCoup=args.trigger_coupling,
        trigLevel=args.trigger_level,
        trigSlope=args.trigger_slope,
        acquisition=1,
        mdepth=args.mdepth,
        download_mode=mode,
    )
    return scope


def prepare_hardware_scope(scope, args):
    scope.initComm()
    scope.setEdgeTrigger(scope._trigSource, scope._trigSlope,
                         scope._trigCoup, scope._trigLevel)
    for i, channel in enumerate(scope._channels):
        scope.setChannel(channel, scope._chanBand[i], scope._chanCoup[i],
                         scope._chanInv[i], scope._chanImp[i])
        if args.vscale is not None:
            scope.setVertScale(channel, args.vscale)
    if args.hscale is not None:
        scope.setHorScale(args.hscale)
    scope.run()
    scope.setSampAcquisition()
    check = scope.setandcheckmdepth(args.mdepth)
    if check:
        raise RuntimeError("Rigol rejected requested memory depth.")


def benchmark_method(scope, method_name, args):
    rows = []
    method = getattr(scope, method_name)
    for idx in range(args.iterations):
        start = time.perf_counter()
        error = ""
        samples = 0
        vmax = np.nan
        attempts = 1
        vpp = np.nan
        signal_ok = False
        samples_ok = False
        try:
            if method_name == "getchannelsFast":
                values, vmax = method(
                    args.channels,
                    args.mdepth,
                    poll_interval=args.poll_interval,
                    trigger_timeout=args.trigger_timeout,
                    waveform_delay=args.waveform_delay,
                    arm_delay=args.arm_delay,
                    max_retries=args.max_retries,
                    min_vpp=args.min_vpp,
                    waveform_points_timeout=args.waveform_points_timeout,
                )
            else:
                values, vmax = method(args.channels, args.mdepth)
            samples = int(np.asarray(values).shape[-1])
            samples_ok = samples == int(args.mdepth)
            vpp = float(np.ptp(np.asarray(values).reshape(-1)))
            signal_ok = (
                samples_ok
                and (args.signal_vpp_threshold is None
                     or vpp >= args.signal_vpp_threshold)
            )
            if not samples_ok:
                error = f"Invalid sample count: {samples}, expected {args.mdepth}"
            elif args.signal_vpp_threshold is not None and not signal_ok:
                error = (
                    f"Signal Vpp {vpp:.6g} V is below threshold "
                    f"{args.signal_vpp_threshold:.6g} V"
                )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        attempts = int(getattr(scope, "_last_acquisition_attempts", 1))
        elapsed = time.perf_counter() - start
        rows.append({
            "method": method_name,
            "iteration": idx + 1,
            "elapsed_s": elapsed,
            "samples": samples,
            "samples_ok": samples_ok,
            "vpp_v": vpp,
            "signal_ok": signal_ok,
            "attempts": attempts,
            "retries": max(0, attempts - 1),
            "vmax_ch2": float(vmax),
            "error": error,
        })
    return rows


def summarize(rows):
    elapsed = [row["elapsed_s"] for row in rows if not row.get("error")]
    if not elapsed:
        return {
            "n": 0,
            "failures": len(rows),
            "mean_s": float("nan"),
            "median_s": float("nan"),
            "min_s": float("nan"),
            "max_s": float("nan"),
        }
    return {
        "n": len(elapsed),
        "failures": len(rows) - len(elapsed),
        "mean_s": statistics.mean(elapsed),
        "median_s": statistics.median(elapsed),
        "min_s": min(elapsed),
        "max_s": max(elapsed),
    }


def write_csv(path, rows):
    fieldnames = [
        "method", "iteration", "elapsed_s", "samples", "samples_ok",
        "vpp_v", "signal_ok", "attempts", "retries", "vmax_ch2", "error",
    ]
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_channels(text):
    return tuple(int(item.strip()) for item in text.split(",") if item.strip())


def optional_float(text):
    if str(text).lower() in ("none", "skip", "off"):
        return None
    return float(text)


def expand_per_channel(value, channels):
    if "," in value:
        items = tuple(item.strip() for item in value.split(",") if item.strip())
        if len(items) != len(channels):
            raise argparse.ArgumentTypeError(
                "Per-channel values must match the number of channels."
            )
        return items
    return tuple([value] * len(channels))


def parse_methods(text):
    aliases = {
        "legacy": ("legacy", "getchannels"),
        "getchannels": ("legacy", "getchannels"),
        "fast": ("fast", "getchannelsFast"),
        "getchannelsfast": ("fast", "getchannelsFast"),
    }
    methods = []
    for item in text.split(","):
        key = item.strip().lower()
        if not key:
            continue
        if key not in aliases:
            raise argparse.ArgumentTypeError(f"Unknown method: {item}")
        methods.append(aliases[key])
    return methods


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("fake", "hardware"), default="fake")
    parser.add_argument("--transport", choices=("instr", "socket"), default="instr")
    parser.add_argument("--ip", default="192.168.2.2")
    parser.add_argument("--socket-port", type=int, default=5555)
    parser.add_argument("--visa-backend", choices=("pyvisa", "nivisa"),
                        default="pyvisa",
                        help="'pyvisa' uses pyvisa-py; 'nivisa' uses the system NI-VISA library.")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--mdepth", type=int, default=70000)
    parser.add_argument("--channels", type=parse_channels, default=(1,))
    parser.add_argument("--coupling", default="AC",
                        help="Single value or comma-separated per channel.")
    parser.add_argument("--impedance", default="OMEG",
                        help="Single value or comma-separated per channel.")
    parser.add_argument("--bandwidth", default="20M")
    parser.add_argument("--trigger-source", default="CHAN1")
    parser.add_argument("--trigger-coupling", default="AC")
    parser.add_argument("--trigger-level", type=float, default=0.1)
    parser.add_argument("--trigger-slope", default="POS")
    parser.add_argument("--vscale", type=optional_float, default=0.05,
                        help="Vertical scale in V/div. Use --vscale none to skip.")
    parser.add_argument("--hscale", type=optional_float, default=10e-6,
                        help="Horizontal scale in s/div. Use --hscale none to skip.")
    parser.add_argument("--poll-interval", type=float, default=0.005)
    parser.add_argument("--trigger-timeout", type=float, default=5.0)
    parser.add_argument("--waveform-delay", type=float, default=0.01)
    parser.add_argument("--waveform-points-timeout", type=float, default=0.5,
                        help="Seconds to keep polling after :WAV:STAT? is IDLE "
                             "but reports fewer points than requested.")
    parser.add_argument("--arm-delay", type=float, default=0.05,
                        help="Delay after :SINGle before polling trigger status.")
    parser.add_argument("--max-retries", type=int, default=2,
                        help="Retries for empty or rejected fast acquisitions.")
    parser.add_argument("--min-vpp", type=optional_float, default=None,
                        help="Optional minimum Vpp in V for fast acquisitions.")
    parser.add_argument("--signal-vpp-threshold", type=optional_float,
                        default=None,
                        help="Optional Vpp threshold in V used only for benchmark "
                             "quality reporting.")
    parser.add_argument("--methods", type=parse_methods,
                        default=parse_methods("fast"),
                        help="Comma-separated: legacy,fast.")
    parser.add_argument("--output", default=str(HERE / "benchmark_oscrigol_download.csv"))
    args = parser.parse_args()

    args.coupling = expand_per_channel(args.coupling, args.channels)
    args.impedance = expand_per_channel(args.impedance, args.channels)

    all_rows = []
    for mode, method_name in args.methods:
        scope = build_scope(args, mode)
        if args.backend == "fake":
            scope._osci = FakeRigolResource(mdepth=args.mdepth)
        else:
            prepare_hardware_scope(scope, args)
        try:
            rows = benchmark_method(scope, method_name, args)
            all_rows.extend(rows)
            stats = summarize(rows)
            print(
                f"{method_name}: n={stats['n']} "
                f"failures={stats['failures']} "
                f"mean={stats['mean_s']:.4f}s "
                f"median={stats['median_s']:.4f}s "
                f"min={stats['min_s']:.4f}s "
                f"max={stats['max_s']:.4f}s"
            )
            retry_count = sum(row["retries"] for row in rows)
            retried_rows = sum(row["retries"] > 0 for row in rows)
            bad_samples = sum(not row["samples_ok"] for row in rows)
            bad_signal = sum(not row["signal_ok"] for row in rows
                             if args.signal_vpp_threshold is not None)
            print(
                f"  retries_total={retry_count} "
                f"retried_iterations={retried_rows} "
                f"bad_samples={bad_samples} "
                f"bad_signal={bad_signal}"
            )
            for row in rows:
                if row["error"]:
                    print(
                        f"  iteration {row['iteration']} failed after "
                        f"{row['elapsed_s']:.4f}s: {row['error']}"
                    )
        finally:
            if args.backend == "hardware":
                scope.closeComm()

    write_csv(args.output, all_rows)
    print(f"CSV written to {args.output}")


if __name__ == "__main__":
    main()

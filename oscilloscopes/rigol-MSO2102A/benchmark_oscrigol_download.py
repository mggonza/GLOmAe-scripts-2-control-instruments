#!/usr/bin/env python3
"""
Benchmark legacy vs optimized waveform download paths for oscrigol.

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
        self.timeout = 5000
        self.read_termination = None
        self.write_termination = None

    def _delay(self, seconds):
        time.sleep(seconds)

    def write(self, command):
        self._delay(self.command_latency)
        if command.strip().upper() == ":SINGLE":
            self._poll_count = 0

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
                            chunk_size=None):
        self._delay(self.binary_latency)
        phase = np.linspace(0.0, 2.0 * np.pi, self.mdepth, endpoint=False)
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
        visa_backend=None if args.visa_backend == "default" else args.visa_backend,
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
            )
        else:
            values, vmax = method(args.channels, args.mdepth)
        elapsed = time.perf_counter() - start
        rows.append({
            "method": method_name,
            "iteration": idx + 1,
            "elapsed_s": elapsed,
            "samples": int(np.asarray(values).shape[-1]),
            "vmax_ch2": float(vmax),
        })
    return rows


def summarize(rows):
    elapsed = [row["elapsed_s"] for row in rows]
    return {
        "n": len(elapsed),
        "mean_s": statistics.mean(elapsed),
        "median_s": statistics.median(elapsed),
        "min_s": min(elapsed),
        "max_s": max(elapsed),
    }


def write_csv(path, rows):
    fieldnames = ["method", "iteration", "elapsed_s", "samples", "vmax_ch2"]
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("fake", "hardware"), default="fake")
    parser.add_argument("--transport", choices=("instr", "socket"), default="instr")
    parser.add_argument("--ip", default="192.168.2.2")
    parser.add_argument("--socket-port", type=int, default=5555)
    parser.add_argument("--visa-backend", default="@py",
                        help="Use '@py', 'default', or another PyVISA backend.")
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
    parser.add_argument("--arm-delay", type=float, default=0.05,
                        help="Delay after :SINGle before polling trigger status.")
    parser.add_argument("--max-retries", type=int, default=1,
                        help="Retries for empty or rejected fast acquisitions.")
    parser.add_argument("--min-vpp", type=optional_float, default=None,
                        help="Optional minimum Vpp in V for fast acquisitions.")
    parser.add_argument("--output", default=str(HERE / "benchmark_oscrigol_download.csv"))
    args = parser.parse_args()

    args.coupling = expand_per_channel(args.coupling, args.channels)
    args.impedance = expand_per_channel(args.impedance, args.channels)

    all_rows = []
    for mode, method_name in (("legacy", "getchannels"), ("fast", "getchannelsFast")):
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
                f"mean={stats['mean_s']:.4f}s "
                f"median={stats['median_s']:.4f}s "
                f"min={stats['min_s']:.4f}s "
                f"max={stats['max_s']:.4f}s"
            )
        finally:
            if args.backend == "hardware":
                scope.closeComm()

    write_csv(args.output, all_rows)
    print(f"CSV written to {args.output}")


if __name__ == "__main__":
    main()

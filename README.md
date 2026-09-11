# GLOmAe scripts to control instruments

Scripts and notebooks for controlling laboratory instruments from Python.

## Supported instruments

- Oscilloscopes:
  - Rigol MSO2102A
  - Tektronix TDS1012B
  - Tektronix TDS2024B
- Motion controllers:
  - GRBL-based motor controller
  - Newport ESP300
- Function waveform generators:
  - Siglent SDG1032X
- Spectrometers:
  - Hamamatsu C12880MA
- Thermometer/Arduino utilities

## Repository layout

- `oscilloscopes/`: oscilloscope drivers, examples, and programming guides.
- `MotionController/`: motor controller drivers, jog tools, and calibration utilities.
- `FunctionWaveformGenerator/`: waveform generator utilities.
- `spectrometer/`: spectrometer scripts and calibration/reference material.
- `thermometer/`: Arduino and Python thermometer scripts.
- `docs/`: short guides for the main instrument wrappers.

## Documentation

- [Rigol MSO2102A / oscrigol](docs/oscrigol.md): TCP/IP control, legacy and
  optimized waveform downloads, benchmark usage, OIL/PACTER wrappers, and
  vertical auto-adjust notes.
- [GRBL motor controller](docs/motorcontroller.md): serial setup, logical axes,
  movement commands, limits, persisted state, and grid scans.

The Rigol benchmark can be run without hardware using the fake backend:

```bash
python oscilloscopes/rigol-MSO2102A/benchmark_oscrigol_download.py \
  --backend fake \
  --iterations 5 \
  --methods legacy,fast
```

For hardware tests with the current optimized path:

```bash
python oscilloscopes/rigol-MSO2102A/benchmark_oscrigol_download.py \
  --backend hardware \
  --transport socket \
  --visa-backend pyvisa \
  --iterations 32 \
  --methods fast
```

Use `--visa-backend nivisa` to test the installed NI-VISA library.

## Notes

Most scripts are hardware-facing and require the corresponding instrument, communication interface, and Python dependencies such as `pyvisa`, `numpy`, `serial`, and `tqdm`.

Notebooks are included as test benches and examples for specific laboratory
setups. The current Rigol notebooks are:

- `benchmark_oscrigol_download.ipynb`: interactive version of the Rigol
  download benchmark.
- `manual_test_oscrigol.ipynb`: manual smoke test for the base Rigol class.
- `med_oscrigol_oil.ipynb`: template for OIL laboratory measurements.

## Environment

This repository uses Conda as the recommended package manager.

Basic workflow:

```bash
conda create -n glomae-instruments python=3.10
conda activate glomae-instruments
conda install numpy scipy matplotlib jupyter tqdm pyserial
pip install pyvisa pyvisa-py
```

Then open the notebooks or run the Python scripts from the activated environment.

On systems with NI-VISA installed, `oscrigol` can use the system VISA library
with `visa_backend="nivisa"`. The repository default remains
`visa_backend="pyvisa"` because it is easier to reproduce across machines.

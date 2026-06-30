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

## Notes

Most scripts are hardware-facing and require the corresponding instrument, communication interface, and Python dependencies such as `pyvisa`, `numpy`, `serial`, and `tqdm`.

Notebooks are included as test benches and examples for specific laboratory setups.

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

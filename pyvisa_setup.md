# PyVISA in Ubuntu 

Most modern instruments use a standard called SCPI (Standard Commands for Programmable Instruments) for control commands. These commands are text strings (e.g., *IDN? to request identification) that are sent to the instrument through an interface (USB, Serial, Ethernet).
To manage these different interfaces in a unified way in software, there is a specification called VISA (Virtual Instrument Software Architecture). This note explains how to use a Python implementation of VISA.

## 1. Prerequisites: python and pip
It is highly recommended to work within a virtual environment for each project, to avoid dependency conflicts:

'''
conda create -n <env_name>
conda activate <env_name>
python3 --version
conda install pip
pip3 --version
'''

## 2. Install the Core Library: PyVISA
The de facto standard library for instrument control in Python is PyVISA. It provides a unified interface for different backends (VISA implementations). 

'''
pip install pyvisa pyvisa-py pySerial
'''

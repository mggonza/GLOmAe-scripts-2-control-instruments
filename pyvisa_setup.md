# PyVISA in Ubuntu 

Most modern instruments use a standard called SCPI (Standard Commands for Programmable Instruments) for control commands. These commands are text strings (e.g., *IDN? to request identification) that are sent to the instrument through an interface (USB, Serial, Ethernet).
To manage these different interfaces in a unified way in software, there is a specification called VISA (Virtual Instrument Software Architecture). This note explains how to use a Python implementation of VISA.

## 1. Pre-requisites: python and pip
It is highly recommended to work within a virtual environment for each project, to avoid dependency conflicts:

```
conda create -n <env_name>
conda activate <env_name>
python3 --version
conda install pip
pip3 --version
```

## 2. Install the Core Library: PyVISA
The standard library for instrument control in Python is PyVISA. It provides a unified interface for different backends (VISA implementations). 

```
pip install pyvisa pyvisa-py pySerial
```

En construcción:

conda create -n med
conda activate med
conda install pip
sudo addgroup <username> dialout
pip install pyvisa pyvisa-py pyUSB pySerial numpy datetime matplotlib
pip install python-usbtmc
pip install zeroconf
pip install jupyter-lab
pip install psutil

sudo groupadd usbusers
sudo usermod -a -G usbusers researcher
cd /etc/udev/rules.d/
sudo gedit 99-com.rules # Para agregar: SUBSYSTEM=="usb", MODE="0666", GROUP="usbusers"
sudo udevadm control --reload
sudo udevadm trigger
sudo reboot

conda activate med
cd /home/Maximiliano/TestPyVisa/
python3 Scan_rapido.py 
python3 Prueba_TDS1012B.py 

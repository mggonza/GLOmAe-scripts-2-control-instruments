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

## 3. Configuration and Permissions by Interface Type
This is where things vary depending on how you connect the instrument.

### A. Serial Port Control (RS-232, USB-Serial)
Many instruments, especially older or simpler ones use serial communication. USB-to-serial adapters are also common and appear in Linux as serial devices.

* Port Identification: connect your device. In Linux, serial ports usually appear as /dev/ttyS0, /dev/ttyS1, etc. (for native serial ports) or /dev/ttyUSB0, /dev/ttyUSB1, /dev/ttyACM0, etc. (for USB-Serial adapters or instruments that emulate a serial port over USB). You can try to identify them:

  * Disconnect the device. Run: ``` ls /dev/tty*```.
  * Connect the device. Wait a few seconds. Run  ```ls /dev/tty*``` again. The new device /dev/ttyUSBx or /dev/ttyACMx is likely your instrument.
  * You can also use ```dmesg | tail`` just after connecting the device to see what name the kernel assigned to it.
    
* Permissions: by default, access to serial ports in Linux requires special permissions. Typically, these devices belong to the dialout group. You must add your user to this group:

```
sudo usermod -a -G dialout $USER
```


En construcción:

```
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
```

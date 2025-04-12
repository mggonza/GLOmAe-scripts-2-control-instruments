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

* Port Identification: connect your device. In Linux, serial ports usually appear as ```/dev/ttyS0```, ```/dev/ttyS1```, etc. (for native serial ports) or ```/dev/ttyUSB0```, ```/dev/ttyUSB1```, ```/dev/ttyACM0```, etc. (for USB-Serial adapters or instruments that emulate a serial port over USB). You can try to identify them:

  * Disconnect the device. Run: ``` ls /dev/tty*```.
  * Connect the device. Wait a few seconds. Run  ```ls /dev/tty*``` again. The new device ```/dev/ttyUSBx``` or ```/dev/ttyACMx``` is likely your instrument.
  * You can also use ```dmesg | tail``` just after connecting the device to see what name the kernel assigned to it.
    
* Permissions: by default, access to serial ports in Linux requires special permissions. Typically, these devices belong to the dialout group. You must add your user to this group:

```
sudo usermod -a -G dialout $USER
```
* Important: after running this command, you must log out and log back in (or reboot) for the group change to take effect. You can check if you belong to the group with the groups command.

* Python usage (with PyVISA):

```
import pyvisa

rm = pyvisa.ResourceManager('@py') # Use the pyvisa-py backend
# Replace '/dev/ttyUSB0' with your actual port
# Also adjust baud_rate, data_bits, parity, and stop_bits according to the instrument manual
try:
    # The resource format is ASRL[address]::INSTR
    instrument = rm.open_resource('ASRL/dev/ttyUSB0::INSTR',
                                  baud_rate=9600,
                                  data_bits=8,
                                  parity=pyvisa.constants.Parity.none,
                                  stop_bits=pyvisa.constants.StopBits.one)
    instrument.read_termination = '\n' # Or '\r\n', depending on the instrument
    instrument.write_termination = '\n'

    # Example: Ask for ID
    instrument.write('*IDN?')
    id = instrument.read()
    print(f"ID: {id}")

    # Other commands...
    # instrument.write('SPECIFIC_COMMAND')
    # response = instrument.read()
    # value = instrument.query('OTHER_COMMAND?') # write + read

    instrument.close()
    print("Communication closed.")
except pyvisa.errors.VisaIOError as e:
    print(f"VISA error: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
finally:
    rm.close()
```

### B. USB Control (USBTMC or Vendor-Specific)
Many modern instruments (oscilloscopes, function generators) use USB directly, often following the USBTMC (USB Test & Measurement Class) protocol.

* Device Identification: Connect the instrument. Use ```lsusb``` to view connected USB devices. Look for something that resembles your instrument (it may show the manufacturer or model name).

```
lsusb
```

This will give you the ```VendorID``` and ```ProductID``` (e.g., ```Bus 001 Device 005: ID 0957:179a Agilent Technologies```). These IDs are useful for udev rules.

* Permissions (```udev```): as with serial ports, you need permissions to directly access the USB device. The standard and persistent way to do this in Linux is through ```udev``` rules. You'll need to create a rules file in ```/etc/udev/rules.d/```.

  * Get ```VendorID``` and ```ProductID```: Use ```lsusb```. For example, ```0957``` and ```179a```.
  * Create the rules file: Create a file, for example, ```/etc/udev/rules.d/99-instruments.rules```. The name must begin with a number (priority) and end with ```.rules```.

```
sudo gedit /etc/udev/rules.d/99-instruments.rules
```

  * Add the rule: inside the file, add one line for each device type. Set the ```VendorID```, ```ProductID```, and the ```GROUP```. The ```usbtmc``` group is a good choice, but ```plugdev``` or ```dialout``` are also common. Make sure your user belongs to the group you choose.

Code Snippet

```
# Rule for an Agilent/Keysight device (example)
SUBSYSTEM=="usb", ATTR{idVendor}=="0957", ATTR{idProduct}=="179a", MODE="0666", GROUP="usbtmc"

# Rule for another device, using a different group if necessary
# SUBSYSTEM=="usb", ATTR{idVendor}=="xxxx", ATTR{idProduct}=="yyyy", MODE="0660", GROUP="plugdev"

"""
SUBSYSTEM=="usb": Applies to USB devices.
ATTR{idVendor}=="0957": Matches the vendor ID (hexadecimal).
ATTR{idProduct}=="179a": Matches the product ID (hexadecimal).
MODE="0666": Sets the permissions (read/write for everyone). ```0660``` would give read/write to the owner and group.
ROUP="usbtmc": Assigns the device to the usbtmc group. If this group doesn't exist, create it (```sudo groupadd usbtmc```)
and add your user to it (```sudo usermod -a -G usbtmc $USER```).
Remember to log out and back in after adding yourself to the group.
"""

```

  * Apply the rules:

```
sudo udevadm control --reload-rules
sudo udevadm trigger
```

  * Disconnect and reconnect the instrument for the rule to be applied correctly.




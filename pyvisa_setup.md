# PyVISA in Ubuntu 

Most modern instruments use a standard called SCPI (Standard Commands for Programmable Instruments) for control commands. These commands are text strings (e.g., *IDN? to request identification) that are sent to the instrument through an interface (USB, Serial, Ethernet).
To manage these different interfaces in a unified way in software, there is a specification called VISA (Virtual Instrument Software Architecture). This note explains how to use a Python implementation of VISA.

## 1. Pre-requisites: python and pip
It is highly recommended to work within a virtual environment for each project, to avoid dependency conflicts (assuming previous installation of miniconda):

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
    
  * Python usage (with PyVISA): ```PyVISA``` can automatically find ```USBTMC``` devices. The resource format is typically ```USB[bus]::[device]::[interface]::INSTR``` or more commonly using ```VendorID``` and ```ProductID.```

```
import pyvisa
rm = pyvisa.ResourceManager('@py') # Use the pyvisa-py backend
# List all resources found by pyvisa-py
print("Resources found:")
print(rm.list_resources())

# Try connecting using VendorID and ProductID (replace with your own)
# Format: USB::VENDOR_ID::PRODUCT_ID::SERIAL_NUMBER::INSTR (Serial Number is optional)
try:
    # Example for the Agilent/Keysight from the lsusb example
    # IDs must be decimal or hexadecimal with a 0x prefix
    instrument = rm.open_resource('USB::0x0957::0x179a::INSTR')
    # Or try connecting with the resource name listed by list_resources()
    # instrument = rm.open_resource('USB0::0x0957::0x179a::MY12345678::0::INSTR')

    # Configure terminations if needed (often not for USBTMC)
    # instrument.read_termination = '\n'
    # instrument.write_termination = '\n'

    # Query for ID
    id = instrument.query('*IDN?')

    print(f"ID: {id}")

    # Other commands...
    # value = instrument.query('MEAS:VOLT:DC?')
    # print(f"DC voltage: {value}")

    instrument.close()
    print("Communication closed.")
except pyvisa.errors.VisaIOError as e:
    print(f"Could not connect or communicate. VISA Error: {e}")
    print("Check:")
    print("- Is the device connected and powered on?")
    print("- Were udev rules applied correctly (if necessary)?")
    print("- Does your user belong to the correct group (e.g., usbtmc, plugdev, dialout)? (Requires re-login)")
    print("- Are the VendorIDs/ProductIDs correct?")
    print("- Are you using the '@py' backend?")
except Exception as e:
    print(f"An error occurred: {e}")
finally:
    rm.close()
```

  * Backend Note: If ```pyvisa-py``` (@py) doesn't work for your USB device (especially if it's complex or requires a specific driver), you may need to install the National Instruments NI-VISA backend (which has its own installation process and permissions setup on Linux) and then use ```pyvisa``` without specifying @py (```rm = pyvisa.ResourceManager()```). However, always try ```pyvisa-py``` first.

### C. Control over Ethernet (LAN/LXI)
Many modern instruments also have an Ethernet port and support control over LAN, often using the LXI (LAN eXtensions for Instrumentation) standard.

* Network Configuration:
    * Connect the instrument to the same network as your Ubuntu notebook.
    * Make sure the instrument has a valid IP address on that network. It can be obtained via DHCP, or you can configure a static IP (see the instrument's manual). You'll need to know that IP address.
    * Make sure your notebook can "see" the instrument on the network. You can try pinging ```INSTRUMENT_IP_ADDRESS``` from the Ubuntu terminal.
    * Firewall: if you have a firewall enabled in Ubuntu (```ufw``` or another), make sure it allows outgoing communication to the instrument and incoming communication if the instrument needs to initiate a connection (less common). Typically, for protocols like VXI-11 or Sockets, you only need to allow outgoing traffic or established connections. Common ports are 111 (portmapper), and other dynamic ports for VXI-11, or a specific TCP port (e.g., 5025) for Sockets communication.

 * Permissions: generally, no special OS-level permissions are required on Linux to open network connections from a user application, unless you attempt to use privileged ports (less than 1024), which is rare for instruments.

 * Usage in Python (with PyVISA): ```pyvisa-py``` supports TCPIP Socket and VXI-11 communication.

```
import pyvisa

rm = pyvisa.ResourceManager('@py') # Use the pyvisa-py backend
# Replace '192.168.1.100' with your instrument's actual IP
instrument_ip = '192.168.1.100'

# Try connecting using TCPIP Socket (common on many modern instruments)
# The default port is usually 5025 for SCPI-RAW / HiSLIP. See the manual.
try:
    # Socket format: TCPIP[board]::host_address[::port]::SOCKET
    instrument = rm.open_resource(f'TCPIP::{instrument_ip}::5025::SOCKET',
                                  read_termination='\n',
                                  write_termination='\n')
    print(f"Connected to {instrument_ip} via Socket.")
    # Sometimes you don't need to specify a port and SOCKET:
    # instrument = rm.open_resource(f'TCPIP::{instrument_ip}::INSTR')

    # Request identification
    identification = instrument.query('*IDN?')
    print(f"Identification: {identification}")

    # Other commands...
    instrument.close()
    print("Communication closed.")

except pyvisa.errors.VisaIOError as e_sock:
    print(f"Error connecting via Socket: {e_sock}")
    print("Attempting to connect via VXI-11 (older)...")
    # Attempt to connect using VXI-11 (common on older LXI instruments)
try:
    # VXI-11 format: TCPIP[board]::host_address[::lan_device_name]::INSTR
    # lan_device_name is usually 'inst0' or 'instr0', but can vary.
    instrument = rm.open_resource(f'TCPIP::{instrument_ip}::inst0::INSTR')
    print(f"Connected to {instrument_ip} via VXI-11.")

    identification = instrument.query('*IDN?')
    print(f"Identification: {identification}")

    instrument.close()
    print("Communication closed.")
except pyvisa.errors.VisaIOError as e_vxi:
    print(f"Error connecting via VXI-11: {e_vxi}")
    print("Could not connect to the instrument via Ethernet.")
    print("Verify:")
    print("- Is the IP correct?")
    print("- Is the instrument on the network and turned on?")
    print("- Is there network connectivity (ping)?")
    print("- Is the firewall blocking the connection?")
    print("- Is the protocol (Socket/VXI-11) and port/name are correct (see manual)?")
except Exception as e:
    print(f"An error occurred: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
finally:
    rm.close()
```

## 4. General Steps and Tips

### 4.1 Consult the Manual: 
Your instrument's programming manual is essential. It will tell you what interfaces it supports, what protocols it uses (USBTMC, Serial, VXI-11, Sockets), the communication parameters (baud rate, etc.), and the complete list of SCPI commands it understands.

### 4.2 Start Simple: 
Always try to obtain the ID (```*IDN?```) first. If that works, basic communication is established.

### 4.3 Handle Errors:
Use ```try...except``` blocks to catch possible communication errors (```pyvisa.errors.VisaIOError```) or other errors.

### 4.4 Close Resources: 
Make sure to close the connection to the instrument (```instrument.close()```) and the resource manager (```rm.close()```) when you're done, preferably using ```try...finally``` blocks.

### 4.5 ** Timeouts:** 
PyVISA allows you to configure timeouts (```instrument.timeout = 5000 # 5 seconds in milliseconds```). Adjust them if you expect slow responses.

### 4.6 Experiment: 
```rm.list_resources()``` is your friend to see what PyVISA detects.

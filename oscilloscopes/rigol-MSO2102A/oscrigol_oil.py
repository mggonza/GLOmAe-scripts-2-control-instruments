import time
from datetime import datetime
from pathlib import Path

import numpy as np
from oscrigol import oscrigol


###############################################################################
def oil_med(
    Nmed=1,
    acq=16,
    mdepth=70000,
    saveresults=True,
    ip_address="192.168.2.2",
    transport="socket",
    use_socket=None,
    visa_backend="pyvisa",
    download_mode="fast",
    poll_interval=0.005,
    trigger_timeout=5.0,
    waveform_delay=0.01,
    waveform_points_timeout=0.5,
    arm_delay=0.05,
    max_retries=2,
    min_vpp=None,
    output_dir="./Mediciones/",
    serial_comm="/dev/ttyUSB0",
    baud_rate=9600,
    measurement_pause=0.1,
):
    """
    Script to obtain OIL measurements.

    Parameters
    ----------
    Nmed : int
        Number of measurements.
    acq : int
        Number of oscilloscope acquisitions to average per measurement.
    mdepth : int
        Number of samples to download per acquisition.
    saveresults : bool
        If True, save partial results after every measurement.
    ip_address : str
        Rigol MSO2102A IP address.
    transport : str
        "socket" for raw sockets or "instr" for VXI-11/INSTR.
    use_socket : bool
        Compatibility option. If set, overrides transport.
    visa_backend : str
        "nivisa" for NI-VISA or "pyvisa" for pyvisa-py.
    download_mode : str
        "fast" uses the optimized single-trigger download in oscrigol.py.

    Returns
    -------
    t : ndarray
        Time axis, shape (Nt,).
    MV : ndarray
        Optoacoustic voltage signals, shape (Nmed, Nt).
    E : ndarray
        Laser energy measurements, shape (Nmed,).
    T : ndarray
        Elapsed time, T1, air temperature, relative humidity and T2,
        shape (Nmed, 5).
    """

    if use_socket is None:
        use_socket = transport == "socket"

    scope = oscrigol_oil(
        ip_address=ip_address,
        use_socket=use_socket,
        visa_backend=visa_backend,
        download_mode=download_mode,
        poll_interval=poll_interval,
        trigger_timeout=trigger_timeout,
        waveform_delay=waveform_delay,
        waveform_points_timeout=waveform_points_timeout,
        arm_delay=arm_delay,
        max_retries=max_retries,
        min_vpp=min_vpp,
    )
    scope.config(acquisition=acq, mdepth=mdepth, download_mode=download_mode)

    arduino = createArduino(serial_comm=serial_comm, baud_rate=baud_rate)

    cte = 1 / (0.08 * 0.08 * 2) * (1 - 0.08 * 2) / 1.086e4
    cte2 = cte

    Nt = int(mdepth)
    MV = np.zeros((Nmed, Nt))
    E = np.zeros((Nmed,))
    T = np.zeros((Nmed, 5))

    now = datetime.now()
    filename = "medOIL_" + now.strftime("%d-%b-%Y-%H:%M:%S")
    output_path = Path(output_dir)
    if saveresults:
        output_path.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    t = np.zeros((Nt,))

    for i in range(Nmed):
        print(f"Medicion: {i + 1}")

        t, v1, v2m = scope()
        Tw, Ta, RH, T2 = medtemphum(arduino)

        TT = time.perf_counter() - start

        MV[i, :] = v1
        E[i] = v2m * cte2
        T[i, 0] = TT
        T[i, 1] = Tw
        T[i, 2] = Ta
        T[i, 3] = RH
        T[i, 4] = T2

        if saveresults:
            np.savez(output_path / f"{filename}.npz", t=t, MV=MV, E=E, T=T)

        if measurement_pause > 0:
            time.sleep(measurement_pause)

    return t, MV, E, T


###############################################################################
def plotresults(t, MV, E, T):
    import matplotlib.pyplot as plt

    plt.figure()
    plt.title("All measured signals")
    for i in range(MV.shape[0]):
        plt.plot(t * 1e6, MV[i, :] * 1e3)
        plt.grid(linestyle="--")
        plt.xlabel("time [us]")
        plt.ylabel("Amplitude [mV]")

    plt.figure()
    i = 0
    plt.title("Averaged signal vs 1st measured signal")
    plt.plot(t * 1e6, MV[i, :] * 1e3, label="signal " + str(i + 1))
    plt.plot(t * 1e6, np.mean(MV, axis=0) * 1e3, label="averaged signal")
    plt.grid(linestyle="--")
    plt.xlabel("time [us]")
    plt.ylabel("Amplitude [mV]")
    plt.legend()

    plt.figure()
    plt.title("Laser energy")
    plt.plot(T[:, 0] / 60, E * 1e3, "s-")
    plt.grid(linestyle="--")
    plt.xlabel("elapsed time [min]")
    plt.ylabel("Energy laser [mJ]")

    plt.figure()
    plt.title("Environment variables")
    plt.plot(T[:, 0] / 60, T[:, 1], "*-", label="T1 [C]")
    plt.plot(T[:, 0] / 60, T[:, 4], "s-", label="T2 [C]")
    plt.plot(T[:, 0] / 60, T[:, 2], "o-", label="Air temp [C]")
    plt.grid(linestyle="--")
    plt.xlabel("elapsed time [min]")
    plt.ylabel("Temperature [C]")
    plt.legend(title="Air humidity: " + str(np.round(np.mean(T[:, 3]), 1)) + " %")

    return


###############################################################################
def createArduino(serial_comm="/dev/ttyUSB0", baud_rate=9600, startup_wait=2):
    import serial

    arduino = serial.Serial(serial_comm, baud_rate, timeout=2)
    time.sleep(startup_wait)
    return arduino


###############################################################################
def medtemphum(arduino):
    # t1, t2 -> DS18B20; tdht, hum -> DHT11.
    arduino.reset_input_buffer()
    arduino.reset_output_buffer()
    arduino.write(b"R")
    arduino.flush()
    time.sleep(1)
    line = arduino.readline().decode().strip()
    if line:
        try:
            t1, t2, tdht, hum = map(float, line.split(","))
            return t1, tdht, hum, t2
        except ValueError:
            pass
    return np.nan, np.nan, np.nan, np.nan


###############################################################################
class oscrigol_oil(oscrigol):
    """
    OIL-oriented wrapper around the tested oscrigol implementation.

    It keeps the original OIL defaults and public method names, but delegates
    VISA communication, waveform download, retries and validation to oscrigol.py.
    """

    def __init__(
        self,
        ip_address="192.168.2.2",
        transport="socket",
        use_socket=None,
        socket_port=5555,
        visa_backend="pyvisa",
        download_mode="fast",
        poll_interval=0.005,
        trigger_timeout=5.0,
        waveform_delay=0.01,
        waveform_points_timeout=0.5,
        arm_delay=0.05,
        max_retries=2,
        min_vpp=None,
    ):
        if use_socket is None:
            use_socket = transport == "socket"

        super().__init__(
            ip_address=ip_address,
            use_socket=use_socket,
            socket_port=socket_port,
            visa_backend=visa_backend,
        )
        self._fast_options = {
            "poll_interval": poll_interval,
            "trigger_timeout": trigger_timeout,
            "waveform_delay": waveform_delay,
            "waveform_points_timeout": waveform_points_timeout,
            "arm_delay": arm_delay,
            "max_retries": max_retries,
            "min_vpp": min_vpp,
        }
        self.config(download_mode=download_mode)

    def config(
        self,
        acquisition=1,
        mdepth=70000,
        channels=(1, 2),
        chanBand=("20M", "20M"),
        chanCoup=("AC", "DC"),
        chanInv=("OFF", "OFF"),
        chanImp=("FIFT", "OMEG"),
        trigSource="EXT",
        trigCoup="AC",
        trigLevel=0.5,
        trigSlope="POS",
        download_mode=None,
    ):
        super().config(
            channels=channels,
            chanBand=chanBand,
            chanCoup=chanCoup,
            chanInv=chanInv,
            chanImp=chanImp,
            trigSource=trigSource,
            trigCoup=trigCoup,
            trigLevel=trigLevel,
            trigSlope=trigSlope,
            acquisition=acquisition,
            mdepth=mdepth,
            download_mode=download_mode,
        )
        return

    def getHorvalues(self, mdepth):
        return self.getHorValues(mdepth)

    def getVertvalues(self, channel, mem_depth):
        return self.getVertValues(channel, mem_depth)

    def getchannels(self, channels, mdepth):
        if self._download_mode in ("fast", "single", "optimized"):
            return self.getchannelsFast(channels, mdepth, **self._fast_options)
        return super().getchannels(channels, mdepth)

    def getTempHum(self, arduino):
        return medtemphum(arduino)

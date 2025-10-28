import pyvisa
import numpy as np
import time


class Oscrigol(object):
    """
    Class for handling Rigol MSO2102A oscilloscopes using PyVISA TCP/IP interface.
    Compatible with the GLOmAe structure (mirrors Tektronix osctck.py design).
    """

    def __init__(self, ip_address="192.168.2.2"):
        # Resource string for VISA-TCPIP interface
        self._resource = f"TCPIP0::{ip_address}::INSTR"
        self._channels = (1,)
        self._triggerSource = 'CHAN1'
        self._triggerLevel = 0.0
        self._triggerSlope = 'POS'
        self._triggerMode = 'NORM'
        self._triggerCoup = 'DC'
        self._acquisition = 1
        self._vAutoScale = False
        self._chanband = 'OFF'
        self._chaninv = 'OFF'


    # Main call replicating Tektronix behavior
    def __call__(self):
        self.initComm()
        self.setEdgeTrigger(
            self._triggerSource, self._triggerSlope,
            self._triggerMode, self._triggerCoup,
            self._triggerLevel
        )

        self._osci.write(f":CHAN{self._channels[0]}:BWLimit {self._chanband}")
        self._osci.write(f":CHAN{self._channels[0]}:INV {self._chaninv}")

        self.run()
        self.setAcquisition(acqMode=1)

        # Vertical autoscale option
        if self._vAutoScale:
            for _ in range(2):
                self.setAcquisition(1)
                vScale = self.getVertScale(self._channels[0])
                maxValue = np.max(np.abs(self.getVertValues(self._channels[0])))
                vScale = maxValue / 3.5 if maxValue > 0 else vScale
                self.setVertScale(self._channels[0], vScale)

        if self._acquisition != 1:
            self.setAcquisition(self._acquisition)

        self.stop()
        values = self.getHorValues(self._channels[0])
        for chNum in self._channels:
            values = np.vstack((values, self.getVertValues(chNum)))

        self.run()
        self.closeComm()
        return values


    # Communication control
    def initComm(self):
        self._osci = pyvisa.ResourceManager().open_resource(self._resource)
        self._osci.timeout = 5000
        self._osci.write(":WAV:FORM BYTE")
        self._osci.write(":WAV:MODE NORM")
        self._osci.write(":WAV:POIN 1400")  # number of points per waveform


    def closeComm(self):
        self._osci.close()


    # Configuration
    def config(self, channels=(1,), triggerSource='CHAN1', triggerLevel=0.0,
               triggerSlope='POS', triggerMode='NORM', triggerCoup='DC',
               acquisition=1, vAutoScale=False, chanband='OFF', chaninv='OFF'):
        self._channels = channels
        self._triggerSource = triggerSource
        self._triggerLevel = triggerLevel
        self._triggerSlope = triggerSlope
        self._triggerCoup = triggerCoup
        self._acquisition = acquisition
        self._vAutoScale = vAutoScale
        self._triggerMode = triggerMode
        self._chanband = chanband
        self._chaninv = chaninv


    # Vertical configuration
    def setVertScale(self, channel, vScale):
        self._osci.write(f":CHAN{channel}:SCAL {vScale}")

    def getVertScale(self, channel):
        return float(self._osci.query(f":CHAN{channel}:SCAL?"))

    # Horizontal configuration
    def setHScale(self, horizontalScale, zero=0):
        self._osci.write(f":TIM:SCAL {horizontalScale}")
        self._osci.write(f":TIM:OFFS {zero}")

    # Acquisition control
    def run(self):
        self._osci.write(":RUN")

    def stop(self):
        self._osci.write(":STOP")

    def setAcquisition(self, acqMode):
        if acqMode == 1:
            self.setSampAcquisition()
        elif acqMode in [4, 16, 64, 128]:
            self.setAvgAcquisition(acqMode)

    def setAvgAcquisition(self, nAvg):
        self._osci.write(":ACQ:TYPE AVER")
        self._osci.write(f":ACQ:AVER {nAvg}")
        time.sleep(2)

    def setSampAcquisition(self):
        self._osci.write(":ACQ:TYPE NORM")
        time.sleep(1)

    # Trigger configuration
    def setEdgeTrigger(self, source="CHAN1", slope="POS", mode="NORM",
                       coupling="DC", level=0.0):
        self._osci.write(":TRIG:MODE EDGE")
        self._osci.write(f":TRIG:EDGE:SOUR {source}")
        self._osci.write(f":TRIG:EDGE:SLOP {slope}")
        self._osci.write(f":TRIG:EDGE:COUP {coupling}")
        self._osci.write(f":TRIG:LEV {level}")
        self._osci.write(f":TRIG:MODE {mode}")

    # Data acquisition
    def getVertValues(self, channel, mode='NORMal'):
        """
        Descarga los datos del canal especificado con resolución configurable.
        mode: 'NORM' (display), 'MAX' (máxima memoria), 'RAW' (datos sin procesar)
        """
        self._osci.write(f":WAV:SOUR CHAN{channel}")
        self.setWaveformPointsMode(mode)
    
        preamble = self._osci.query(":WAV:PRE?").split(',')
        yinc = float(preamble[7])
        yorig = float(preamble[8])
        yref = float(preamble[9])
    
        # leer el número de puntos
        npts = self.getWaveformPointsCount()
    
        # forzar formato binario de 1 byte por punto
        self._osci.write(":WAV:FORM BYTE")
    
        # Lectura de datos binarios
        raw = np.array(
            self._osci.query_binary_values(":WAV:DATA?", datatype='B', container=np.array, chunk_size=npts)
        )
        dataY = (raw - yref) * yinc + yorig
        return dataY


    def getHorValues(self, channel, mode='NORMal'):
        """Devuelve el eje temporal sincronizado con la cantidad real de puntos."""
        self._osci.write(f":WAV:SOUR CHAN{channel}")
        self.setWaveformPointsMode(mode)
    
        preamble = self._osci.query(":WAV:PRE?").split(',')
        xinc = float(preamble[4])
        xorig = float(preamble[5])
        xref = float(preamble[6])
    
        npts = self.getWaveformPointsCount()
        dataX = xorig + np.arange(npts) * xinc
        return dataX

    def getID(self):
        return self._osci.query("*IDN?")

    def setupDefault(self):
        self._osci.write(":SYST:FACTory")

    def showChannel(self, channel):
        self._osci.write(f":CHAN{channel}:DISP ON")

    def hideChannel(self, channel):
        self._osci.write(f":CHAN{channel}:DISP OFF")

    def setWaveformPointsMode(self, mode='MAX'):
        """
        Configura el modo de adquisición de puntos de la forma de onda.
        mode: 'NORM' (display), 'MAX' (máxima resolución), o 'RAW' (sin procesar)
        """
        valid_modes = {'NORM': 'NORMal', 'MAX': 'MAXimum', 'RAW': 'RAW'}
        mode_str = valid_modes.get(mode.upper(), 'NORMal')
        self._osci.write(f":WAV:POIN:MODE {mode_str}") 

    def getWaveformPointsMode(self):
        """Devuelve el modo actual de adquisición de puntos."""
        return self._osci.query(":WAV:POIN:MODE?")

    def getWaveformPointsCount(self):
        """Devuelve la cantidad total de puntos configurados en la forma de onda."""
        return int(self._osci.query(":WAV:POIN?"))

    def download_full_waveform(self, channel=1, filename=None):
        self._osci.timeout = 20000
        self._osci.write(":STOP")
        self._osci.write(":ACQuire:TYPE NORMal")
        self._osci.write(":ACQuire:MEMDepth LONG")
        time.sleep(2)
    
        self._osci.write(f":WAVeform:SOURce CHAN{channel}")
        self._osci.write(":WAVeform:POINts:MODE MAXimum")
        self._osci.write(":WAVeform:FORM BYTE")
    
        npts = int(self._osci.query(":WAVeform:POINts?"))
        print(f"Modo MAX activado, descargando {npts} puntos...")
    
        pre = self._osci.query(":WAVeform:PREamble?").split(',')
        xinc, xorig, yinc, yorig, yref = float(pre[4]), float(pre[5]), float(pre[7]), float(pre[8]), float(pre[9])
        raw = np.array(self._osci.query_binary_values(":WAVeform:DATA?", datatype='B', container=np.array))
        v = (raw - yref) * yinc + yorig
        t = xorig + np.arange(len(v)) * xinc
    
        if filename:
            np.savetxt(filename, np.column_stack((t, v)), delimiter=',', header='time,voltage')
            print(f"Guardado en {filename}")
    
        self._osci.write(":RUN")
        return t, v

import pyvisa
import numpy as np
import time
from tqdm import tqdm 

###############################################################################
class oscrigol(object):
    """
    Class for handling Rigol MSO2102A oscilloscopes using PyVISA TCP/IP interface.
    Compatible with the GLOmAe structure (mirrors Tektronix osctck.py design).
    
    Input parameters:
        *Conectivity
        _resource: ip_address='192.168.2.2'
        *Channels
        _channels: (1,) or (2,) or (1,2)
        _chanBand: ('value ch1', 'value ch2')--> value = OFF | OFF; if 'ON' BW == 20 MHz
        _chanCoup: ('value ch1','value ch2')--> value = DC | AC | GND  
        _chanInv: ('value ch1','value ch2')--> value = OFF | ON
        _chanImp: ('value ch1','value ch2')--> value = OMEG|FIFTy
        *Trigger
        _trigSource = 'value' --> value = CHANnel1 | CHANnel2 | EXT | ACLine
        _trigCoup = 'value' --> value = DC |AC | LFReject | HFReject
        _trigLevel = value --> value = float
        _trigSlope = 'value' --> POSitive | NEGative | RFALl
        * Acquisition
        _acquisition = value --> 1 (RAW)
        _mdepth = value --> only 1 channel = AUTO|14000|140000|1400000|14000000|56000000
                            two channels = AUTO|7000|70000|700000|7000000|28000000
    
    Output:
        A numpy array containing
            Row 0: time values
            Row i: vertical values of channel i
    """
    
    ##########################################################################
    def __init__(self, ip_address="192.168.2.2"):
        # Resource string for VISA-TCPIP interface
        self._resource = f"TCPIP0::{ip_address}::INSTR"
        self._channels = (1,)
        self._chanBand = ('OFF',)
        self._chanCoup = ('AC',)
        self._chanInv = ('OFF',)
        self._chanImp = ('OMEG',)
        self._trigSource = 'EXT'
        self._trigCoup = 'AC'
        self._trigLevel = 0.5
        self._trigSlope = 'POS'
        self._acquisition = 1
        self._mdepth = 14000

    ############################
    # Main call
    ############################
    def __call__(self):
        
        # Init communication
        self.initComm()

        # Set Trigger
        self.setEdgeTrigger(self._trigSource, self._trigSlope, self._trigCoup,self._trigLevel)
        
        # Set channels 
        for i in range(len(self._channels)):
            self.setChannel(self._channels[i],self._chanBand[i],self._chanCoup[i],
                         self._chanInv[i], self._chanImp[i])

        # Start acquisition in normal mode and set memory depth
        self.run()
        self.setSampAcquisition()
        mdepth = self._mdepth
        check = self.setandcheckmdepth(mdepth)
        if check:
            self.closeComm()
            values = 0
            return values
        
        # Get Vertical values
        for i in tqdm(range(int(self._acquisition))):
            if i==0:
                MV = self.getchannels(self._channels,mdepth) 
            else:
                MV = MV + self.getchannels(self._channels,mdepth) 
        MV = MV / int(self._acquisition)
                              
        # Get Horizontal values
        values = self.getHorvalues(mdepth)
        values = np.vstack((values, MV)) 
        
        # Close communication
        self.closeComm()
        
        return values

    ############################
    # Communication control
    ############################
    def initComm(self):
        self._osci = pyvisa.ResourceManager().open_resource(self._resource)
        self._osci.timeout = 5000
        self._osci.write(":WAV:FORM BYTE")
        self._osci.write(":WAV:MODE NORM")
        #self._osci.write(":WAV:POIN 1400")  # number of points per waveform
        return

    def closeComm(self):
        self._osci.close()
        return

    def getID(self):
        return self._osci.query("*IDN?")
    
    ############################
    # Configuration
    ############################
    def config(self, channels=(1,), chanBand=('OFF',), chanCoup=('AC',), 
               chanInv=('OFF',), chanImp = ('OMEG',),
               trigSource='CHAN1', trigCoup='AC', triggerLevel=0.0,
               triggerSlope='POS', trigLevel=0.0, trigSlope = 'POS',
               acquisition=1,mdepth=14000):
        
        self._channels = channels
        self._chanBand = chanBand
        self._chanCoup = chanCoup
        self._chanInv = chanInv
        self._chanImp = chanImp
        self._triggerSource = trigSource
        self._triggerCoup = trigCoup
        self._trigLevel = trigLevel
        self._trigSlope = trigSlope
        self._acquisition = acquisition
        self._mdepth = mdepth
        return
    
    ############################
    # Acquisition control
    ############################
    def run(self):
        self._osci.write(":RUN")
        return

    def stop(self):
        self._osci.write(":STOP")
        return

    def setSampAcquisition(self):
        self._osci.write(":ACQ:TYPE NORM")
        time.sleep(1)
        return

    def setandcheckmdepth(self,mdepth):
        self._osci.write(f":ACQ:MDEP {int(mdepth)}")
        time.sleep(1)
        mdepthread = self._osci.query(f":ACQ:MDEP?")
        time.sleep(1)
        if int(mdepthread) != int(mdepth):
            print("The requested memory depth is incorrect.")
            return 1
        else:
            return 0            
   
    ############################    
    # Trigger configuration
    ############################
    def setEdgeTrigger(self, source="CHAN1", slope="POS", coupling="AC", level=0.0):
        self._osci.write(":TRIG:MODE EDGE")
        self._osci.write(f":TRIG:EDG:SOUR {source}")
        self._osci.write(f":TRIG:EDG:SLOP {slope}")
        self._osci.write(f":TRIG:COUP {coupling}")
        self._osci.write(f":TRIG:EDG:LEV {level}")
        self._osci.write(f":TRIG:SWE NORMAL")
        return

    ############################    
    # Vertical configuration
    ############################
    def setChannel(self, channel,chanBand,chanCoup,chanInv,chanImp):
        self._osci.write(f":CHAN{channel}:BWL {chanBand}")
        self._osci.write(f":CHAN{channel}:COUP {chanCoup}")
        self._osci.write(f":CHAN{channel}:INV {chanInv}")
        self._osci.write(f":CHAN{channel}:IMP {chanImp}")
        return 
    
    def getVertScale(self, channel): 
        return float(self._osci.query(f":CHAN{channel}:SCAL?"))

    def getVertOffset(self, channel): 
        return float(self._osci.query(f":CHAN{channel}:OFFS?"))

    def getVertvalues(self, channel, mem_depth):        
        chunk_size = 2**20
        
        self._osci.write(f":WAV:SOUR CHAN{channel}")
        self._osci.write(":WAV:FORM BYTE")
        self._osci.write(":WAV:MODE RAW")
        self._osci.write(f":WAV:POIN {int(mem_depth)}")
        self._osci.write(f":WAV:STAR 1") # preamble in bits 0-10
        self._osci.write(f":WAV:STOP {int(mem_depth)}")
        self._osci.write(":WAV:RES")
        self._osci.write(":WAV:BEG")
        time.sleep(1)

        raw = self._osci.query_binary_values(":WAV:DATA?", datatype='B', 
                                             container=np.array, 
                                             chunk_size=chunk_size)
        values = np.array(raw)
        vscale = self.getVertScale(channel)
        offset = self.getVertOffset(channel)
        ref = 127.0
        div = 25.4
        # IMPORTANT: The vertical axis has 10 divisions, 
        #            but only 8 are visible on the screen.
        
        values = (values*1.0 - ref)/div * vscale - offset
        return values
    
    def getchannels(self, channels, mdepth):
        time.sleep(1) # wait until the acquisition is completed
        self.stop()
        for i in range(len(channels)):
            if i<1:
                MV = self.getVertvalues(channels[i], mdepth)
            else:
                if i == 0:
                    MV = self.getVertvalues(channels[i], mdepth)
                else:
                    MV = np.vstack((MV, self.getVertvalues(self._channels[i], mdepth))) 
        self.run()
        return MV
    
    ############################    
    # Horizontal configuration
    ############################
    def getHorvalues(self, mdepth):
        hscale = float(self._osci.query(":TIMebase:SCALe?"))
        hoffset = float(self._osci.query(":TIMebase:OFFSet?"))
        Srate = float(self._osci.query(":ACQuire:SRATe?"))
        ndiv = 14
        Tscreen = ndiv * hscale
        Ttotal = mdepth / Srate
        if Tscreen < Ttotal:
            print('Warning: the time window is larger than what is shown on the screen!')
            values = np.linspace(-Ttotal/2,Ttotal/2,mdepth) - hoffset
        else:
            values = np.linspace(-Tscreen/2,Tscreen/2,mdepth) - hoffset
        return values

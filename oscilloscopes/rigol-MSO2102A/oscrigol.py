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
        _chanBand: ('value ch1', 'value ch2')--> value = OFF | OFF; if '20M' BW == 20 MHz
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
        values = self.getHorValues(mdepth)
        values = np.vstack((values, MV)) 
        
        # Close communication
        self.closeComm()
        
        return values

    ############################
    # Communication control
    ############################
    def initComm(self):
        self._osci = pyvisa.ResourceManager('@py').open_resource(self._resource)
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
               trigSource='CHAN1', trigCoup='AC', trigLevel=0.0, trigSlope = 'POS',
               acquisition=1,mdepth=14000):
        
        self._channels = channels
        self._chanBand = chanBand
        self._chanCoup = chanCoup
        self._chanInv = chanInv
        self._chanImp = chanImp
        self._trigSource = trigSource
        self._trigCoup = trigCoup
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
        time.sleep(0.5)
        return

    def setandcheckmdepth(self,mdepth):
        self._osci.write(f":ACQ:MDEP {int(mdepth)}")
        time.sleep(0.5)
        mdepthread = self._osci.query(f":ACQ:MDEP?")
        time.sleep(0.5)
        if int(mdepthread) != int(mdepth):
            print("The requested memory depth is incorrect.")
            return 1
        else:
            return 0            
   
    def setPeakAcquisition(self):
        self._osci.write(":ACQ:TYPE PEAK")
        time.sleep(0.5)
        return

    def setAvgAcquisition(self, nAvg=16):
        self._osci.write(":ACQ:TYPE AVER")
        self._osci.write(f":ACQ:AVER {int(nAvg)}")
        time.sleep(0.5)
        return

    def setAcquisitionMode(self, mode="PEAK", nAvg=16):
        mode = mode.upper()

        if mode in ("NORM", "NORMAL", "SAMP", "SAMPLE"):
            self.setSampAcquisition()

        elif mode in ("PEAK", "PDET", "PEAKDETECT"):
            self.setPeakAcquisition()

        elif mode in ("AVG", "AVER", "AVERAGE"):
            self.setAvgAcquisition(nAvg)

        else:
            raise ValueError("mode must be 'NORM', 'PEAK' or 'AVG'")

        return
    
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
    # Horizontal configuration
    ############################
    def getHorValues(self, mdepth):
        hscale = float(self._osci.query(":TIMebase:SCALe?"))
        hoffset = float(self._osci.query(":TIMebase:OFFSet?"))
        Srate = float(self._osci.query(":ACQuire:SRATe?"))
        ndiv = 14
        Tscreen = ndiv * hscale
        Ttotal = mdepth / Srate
        if Tscreen < Ttotal:
            print('Warning: the time window is larger than what is shown on the screen!')
            values = np.linspace(-Ttotal/2,Ttotal/2,mdepth) + hoffset
        else:
            values = np.linspace(-Tscreen/2,Tscreen/2,mdepth) + hoffset
        return values
    
    def setHorScale(self, hScale, zero=0):
        self._osci.write(f":TIM:SCAL {hScale}")
        self._osci.write(f":TIM:OFFS {zero}")
        return

    ############################    
    # Vertical configuration
    ############################
    def getVertScale(self, channel): 
        return float(self._osci.query(f":CHAN{channel}:SCAL?"))

    def getVertOffset(self, channel): 
        return float(self._osci.query(f":CHAN{channel}:OFFS?"))

    def getVertValues(self, channel, mem_depth,delay_time=1):        
        chunk_size = 2**20
        
        self._osci.write(f":WAV:SOUR CHAN{channel}")
        self._osci.write(":WAV:FORM BYTE")
        self._osci.write(":WAV:MODE RAW")
        self._osci.write(f":WAV:POIN {int(mem_depth)}")
        self._osci.write(f":WAV:STAR 1") # preamble in bits 0-10
        self._osci.write(f":WAV:STOP {int(mem_depth)}")
        self._osci.write(":WAV:RES")
        self._osci.write(":WAV:BEG")
        #time.sleep(0.5)
        time.sleep(delay_time)

        raw = self._osci.query_binary_values(":WAV:DATA?", datatype='B', 
                                             container=np.array, 
                                             chunk_size=chunk_size)
        time.sleep(delay_time)
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
        self.run()
        time.sleep(1) # wait until the acquisition is completed
        self.stop()
        for i in range(len(channels)):
            if i == 0:
                MV = self.getVertValues(channels[i], mdepth)
            else:
                MV = np.vstack((MV, self.getVertValues(self._channels[i], mdepth))) 
        self.run()
        return MV
    
    def getVMax(self, channel):
        vmax=float(self._osci.query(f":MEASure:VMAX? CHANnel{channel}"))
        return vmax

    def getVMin(self, channel):
        vmin = float(self._osci.query(f":MEASure:VMIN? CHANnel{channel}"))
        return vmin
    
    def setVertScale(self, channel, vScale):
        self._osci.write(f":CHAN{channel}:SCAL {vScale}")
        return

    def setVertOffset(self, channel, offset):
        self._osci.write(f":CHAN{channel}:OFFS {offset}")
        return

    def setChannel(self, channel,chanBand,chanCoup,chanInv,chanImp):
        self._osci.write(f":CHAN{channel}:BWL {chanBand}")
        self._osci.write(f":CHAN{channel}:COUP {chanCoup}")
        self._osci.write(f":CHAN{channel}:INV {chanInv}")
        self._osci.write(f":CHAN{channel}:IMP {chanImp}")
        return 
    
    ############################
    # Auto-adjust vertical scale
    ############################

    def _round_scope_scale(self, scale):
        if scale <= 0:
            return scale

        steps = np.array([1, 2, 5, 10])
        exponent = np.floor(np.log10(scale))
        mantissa = scale / 10**exponent
        rounded = steps[np.searchsorted(steps, mantissa)] * (10**exponent)

        return rounded 

    def _is_invalid_measurement(self, value, invalid_threshold=1e30):
        return (not np.isfinite(value)) or (abs(value) > invalid_threshold)

    def _safe_get_vmin_vmax(self, channel):
        vmin = self.getVMin(channel)
        vmax = self.getVMax(channel)

        invalid_min = self._is_invalid_measurement(vmin)
        invalid_max = self._is_invalid_measurement(vmax)

        return vmin, vmax, invalid_min, invalid_max

    def autoAdjustVertScale(
        self,
        channels=None,
        mode="PEAK",
        n_iter=2,
        target_divisions=7.0,
        min_divisions=4.0,
        max_divisions=7.5,
        use_scope_steps=False,
        min_scale=1e-3,
        max_scale=10.0,
        offset_sign=-1,
        invalid_threshold=1e30,
        recovery_scale_factor=2.0,
        recovery_offset_divisions=2.0,
        acq_wait=0.5,
        settle_wait=0.2,
        verbose=True
    ):
        """
        Autoajuste condicional de escala vertical y offset.

        La función:
        - mide VMAX y VMIN usando mediciones internas del Rigol;
        - calcula cuántas divisiones verticales ocupa la señal;
        - reajusta la escala solo si es necesario;
        - detecta saturación/fuera de rango (~9.9e37);
        - aplica recuperación automática de escala y offset.

        Parámetros
        ----------
            - channels: canales a procesar; si es None usa self._channels.
            - mode: modo de adquisición usado para medir amplitud ('PEAK' o 'NORM').
            - n_iter: número de iteraciones de autoajuste.
            - target_divisions: cantidad ideal de divisiones verticales ocupadas.
            - min_divisions: límite inferior antes de ampliar señal.
            - max_divisions: límite superior antes de reducir señal.
            - use_scope_steps: si True usa escalas típicas  1-2-5 y sus multiplos.
            - min_scale: escala vertical mínima permitida [V/div].
            - max_scale: escala vertical máxima permitida [V/div].
            - offset_sign: signo usado para calcular offset vertical.
            - invalid_threshold: umbral para detectar mediciones inválidas.
            - recovery_scale_factor: factor aplicado a escala durante recuperación.
            - recovery_offset_divisions: divisiones usadas para mover offset.
            - acq_wait: tiempo de espera para adquirir señal.
            - settle_wait: tiempo de estabilización luego de detener adquisición.
            - verbose: si True imprime información detallada.
        """

        # Si no se especifican canales usar los definidos en config()
        if channels is None:
            channels = self._channels

        # Init communication
        self.initComm()
        
        # Configuración del modo de adquisición
        # PEAK permite capturar excursiones máximas y mínimas
        if mode.upper() in ("PEAK", "PDET", "PEAKDETECT"):
            self.setPeakAcquisition()

        # SAMPLE/NORMAL es más rápido pero menos robusto frente a picos
        elif mode.upper() in ("NORM", "NORMAL", "SAMP", "SAMPLE"):
            self.setSampAcquisition()

        else:
            raise ValueError("Usar mode='PEAK' o mode='NORM'.")

        adjusted = {}

        # Función auxiliar:
        # el Rigol devuelve típicamente ~9.9e37 cuando una medición es inválida
        def is_invalid(value):
            return (not np.isfinite(value)) or (abs(value) > invalid_threshold)

        # Procesar cada canal
        for ch in channels:
        
            adjusted[ch] = False

            # Iteraciones de ajuste si la señal está inicialmente fuera de rango
            for it in range(n_iter):
                # Ejecutar adquisición
                self.run()

                # Esperar captura
                # importante en sistemas sincronizados con láser pulsado
                time.sleep(acq_wait)

                # Congelar adquisición
                self.stop()

                # Esperar estabilización interna del osciloscopio
                time.sleep(settle_wait)

                # Mediciones internas del Rigol
                vmax = self.getVMax(ch)
                vmin = self.getVMin(ch)

                # Detectar mediciones inválidas/fuera de rango
                invalid_max = is_invalid(vmax)
                invalid_min = is_invalid(vmin)

                # Configuración actual del canal
                current_scale = self.getVertScale(ch)
                current_offset = self.getVertOffset(ch)

                if verbose:
                    print(f"\nAutoAdjust vertical - iteración {it+1}/{n_iter}")

                ########################################
                # CASO 1:
                # Medición fuera de rango / saturación
                ########################################
                if invalid_max or invalid_min:

                    # Agrandar escala vertical
                    # (más V/div -> más rango visible)
                    new_scale = current_scale * recovery_scale_factor

                    # Redondear a escalas típicas 1-2-5 si se desea
                    if use_scope_steps:
                        new_scale = self._round_scope_scale(new_scale)

                    # Limitar rango permitido
                    new_scale = max(min_scale, min(max_scale, new_scale))

                    # Estrategias de recuperación de offset
                    if invalid_max and invalid_min:

                        # Señal completamente fuera de pantalla
                        # volver offset al centro
                        new_offset = 0.0

                    elif invalid_max:

                        # Saturación superior:  mover ventana vertical hacia arriba
                        new_offset = current_offset - recovery_offset_divisions * current_scale

                    else:

                        # Saturación inferior: mover ventana vertical hacia abajo
                       new_offset = current_offset + recovery_offset_divisions * current_scale

                    # Aplicar recuperación
                    self.setVertScale(ch, new_scale)
                    self.setVertOffset(ch, new_offset)

                    adjusted[ch] = True

                    if verbose:
                        print(
                            f"CH{ch}: medición fuera de rango "
                            f"(Vmin={vmin:.4g}, Vmax={vmax:.4g})"
                        )

                        print(
                            f"CH{ch}: recuperación -> "
                            f"scale={current_scale:.4g} → {new_scale:.4g} V/div, "
                            f"offset={current_offset:.4g} → {new_offset:.4g} V"
                        )

                    # Pasar al siguiente canal
                    continue

                ################################################
                # CASO 2:
                # Señal válida -> evaluar necesidad de reajuste
                ################################################

                # Tensión pico a pico
                vpp = vmax - vmin

                # Centro vertical de la señal
                vcenter = 0.5 * (vmax + vmin)

                # Cantidad de divisiones verticales ocupadas
                used_div = vpp / current_scale if current_scale > 0 else 0

                # Reajustar solo si la señal es muy chica o muy grande
                need_adjust = (used_div < min_divisions) or (used_div > max_divisions)

                ###########################
                # CASO 2A:
                # Reajuste necesario
                ###########################
                if need_adjust and vpp > 0:

                    # Escala ideal para ocupar target_divisions
                    new_scale = vpp / target_divisions

                    # Redondeo opcional a escalas típicas
                    if use_scope_steps:
                        new_scale = self._round_scope_scale(new_scale)

                    # Limitar rango permitido
                    new_scale = max(min_scale, min(max_scale, new_scale))

                    # Centrar señal verticalmente
                    new_offset = offset_sign * vcenter

                    # Aplicar cambios
                    self.setVertScale(ch, new_scale)
                    self.setVertOffset(ch, new_offset)

                    adjusted[ch] = True

                    if verbose:
                        print(
                            f"CH{ch}: Vmin={vmin:.4g} V, Vmax={vmax:.4g} V, "
                            f"Vpp={vpp:.4g} V, usado={used_div:.2f} div"
                        )
                        print(
                            f"CH{ch}: ajuste -> "
                            f"scale={current_scale:.4g} → {new_scale:.4g} V/div, "
                            f"offset={current_offset:.4g} → {new_offset:.4g} V"
                        )

                    continue

                #############################
                # CASO 2B:
                # No hace falta reajuste
                #############################
                else:
                    if verbose:
                        print(
                            f"CH{ch}: Vmin={vmin:.4g} V, Vmax={vmax:.4g} V, "
                            f"Vpp={vpp:.4g} V, usado={used_div:.2f} div"
                        )
                        print(
                            f"CH{ch}: no requiere ajuste. "
                            f"scale={current_scale:.4g} V/div, "
                            f"offset={current_offset:.4g} V"
                        )

                break

        # Reanudar adquisición continua
        self.run()

        # Close communication
        self.closeComm()

        return adjusted
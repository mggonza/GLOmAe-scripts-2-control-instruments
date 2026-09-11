import numpy as np
import time
from datetime import datetime

try:
    from .oscrigol import oscrigol
except ImportError:
    from oscrigol import oscrigol

###############################################################################
def pacter_med(
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
):
    """
    Scripts to obtain PACTER measurements
    
    	Inputs parameters:
    		Nmed: number of measurements (int)
    		acq: number of acquisitions to perform average (int)
    		mdepth: number of samples to be acquired 7000|70000|700000|7000000|28000000
    	
    	Output:
    		t: time axis (Nt,) [s]
    		MV: voltage signals (Nmed,Nt) [V]
    		E: laser energy measurements (Nmed,) [J]
    		T: elapsed time [s], water temperature [°C], 
            air temperature [°C] and air relative humidity [%] (Nmed,4)  
    
    """
      
    # Crear objeto osciloscopio Rigol
    if use_socket is None:
        use_socket = transport == "socket"

    MSO2102A = oscrigol_pacter(
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
    MSO2102A.config(acquisition=acq, mdepth=mdepth, download_mode=download_mode)

    # Setup arduino
    arduino = createArduino()

    # Constante de conversión medidor energía láser:
    cte = 1/(0.08*0.08*2)*(1-0.08*2)/1.086e4 # J/V
    cte2 = cte*(1-0.08*2)  # J/V
    
    # Variables de salida
    Nt = int(mdepth)
    MV = np.zeros((Nmed,Nt)) # [V]
    E = np.zeros((Nmed,)) # [J]
    T = np.zeros((Nmed,4))
    
    # Nombre del archivo donde se guarda
    now = datetime.now()

    filename = 'medPACTER_' + now.strftime("%d-%b-%Y-%H:%M:%S")
    
    path = './Mediciones/'
    
    # Medición del tiempo transcurrido TT
    start = time.perf_counter()
    
    for i in range(Nmed):
        
        print(f"Medición: {i+1}")
        
        t, v1, v2m = MSO2102A()
    
        # Relevar tiempo pasado, temperatura agua, temperatura aire y humedad
        #Tw, Ta, RH = 0.0, 0.0, 0.0 
        Tw, Ta, RH = medtemphum(arduino)
        #print("Tw =",Tw,"Ta =",Ta,"RH =",RH)
        
        TT = time.perf_counter() - start  # [s]
        
        MV[i,:] = v1
        E[i] = v2m * cte2
        T[i,0] = TT 
        T[i,1] = Tw   
        T[i,2] = Ta   
        T[i,3] = RH   

        if saveresults:
            np.savez(path + filename + '.npz', t=t, MV = MV, E=E, T=T)

        if i < (Nmed-1):
            seguir = input("Presione ENTER para continuar...")

    print("¡Bien hecho, bucle finalizado!")
       
    return t, MV, E, T

###############################################################################
def plotresults(t, MV, E, T):
    import matplotlib.pyplot as plt

    plt.figure()
    for i in range(MV.shape[0]):
        plt.plot(t*1e6,MV[i,:]*1e3)
        plt.grid(linestyle = '--')
        plt.xlabel('elapsed time [us]'); plt.ylabel('Amplitude [mV]')

    plt.figure()
    plt.plot(T[:,0]/60,E*1e3,'s-')
    plt.grid(linestyle = '--')
    plt.xlabel('elapsed time [min]'); plt.ylabel('Energy laser [mJ]')

    plt.figure()
    plt.plot(T[:,0]/60,T[:,1],'*-',label='Water temp (°C)')
    plt.plot(T[:,0]/60,T[:,2],'o-',label='Aire temp (°C)')
    plt.plot(T[:,0]/60,T[:,3],'s-',label='Air humidity (%)')
    plt.grid(linestyle = '--')
    plt.xlabel('elapsed time [min]'); plt.ylabel('Environment variables')
    plt.legend()
    
    return

###############################################################################
def createArduino():
    import serial

    serial_comm = "/dev/ttyUSB0"
    baud_rate = 9600

    # --- Configuración del puerto ---
    arduino = serial.Serial(serial_comm, baud_rate, timeout=2)
    time.sleep(2)  # espera a que Arduino reinicie
    return arduino

###############################################################################
def medtemphum(arduino):
    # t1, t2    -> ds18b20
    # tdht, hum -> DHT11
    arduino.reset_input_buffer()
    arduino.reset_output_buffer()
    arduino.write(b'R')
    arduino.flush()
    time.sleep(1)
    line = arduino.readline().decode().strip()
    if line:
        try:
            t1, t2, tdht, hum = map(float, line.split(","))
            return t1, tdht, hum # descartamos t2
        except ValueError:
            return None
    return None

###############################################################################
class oscrigol_pacter(oscrigol):
    """
    PACTER-oriented wrapper around the tested oscrigol implementation.

    It keeps the original PACTER defaults and public method names, but delegates
    VISA communication, waveform download, retries and validation to oscrigol.py.

    Output:
        t: time axis (Nt,) [s]
        v1: optoacoustic signals (Nt,) [V]
        v2m: maximum value piroelectric signal [V]
    """

    ##########################################################################
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
        self.config(
            download_mode=download_mode,
            poll_interval=poll_interval,
            trigger_timeout=trigger_timeout,
            waveform_delay=waveform_delay,
            waveform_points_timeout=waveform_points_timeout,
            arm_delay=arm_delay,
            max_retries=max_retries,
            min_vpp=min_vpp,
        )

    ############################
    # Configuration
    ############################
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
        poll_interval=None,
        trigger_timeout=None,
        waveform_delay=None,
        cache_vertical_settings=None,
        arm_delay=None,
        require_trigger_state_change=None,
        max_retries=None,
        min_vpp=None,
        waveform_points_timeout=None,
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
            poll_interval=poll_interval,
            trigger_timeout=trigger_timeout,
            waveform_delay=waveform_delay,
            cache_vertical_settings=cache_vertical_settings,
            arm_delay=arm_delay,
            require_trigger_state_change=require_trigger_state_change,
            max_retries=max_retries,
            min_vpp=min_vpp,
            waveform_points_timeout=waveform_points_timeout,
        )
        return

    def getHorvalues(self, mdepth):
        return self.getHorValues(mdepth)

    def getVertvalues(self, channel, mem_depth):
        return self.getVertValues(channel, mem_depth)

    ################################    
    # Medicion temperatura y humedad
    ################################
    def getTempHum(self, arduino):
        Tw, Ta, RH = medtemphum(arduino)
        return Tw, Ta, RH

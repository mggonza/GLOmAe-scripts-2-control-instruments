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
    def __init__(self, ip_address="192.168.2.2", use_socket=False,
                 socket_port=5555, visa_backend='pyvisa'):
        # Resource string for VISA-TCPIP interface.
        # VXI-11/INSTR is kept as the default for backwards compatibility.
        # Raw sockets reduce per-command latency on Rigol scopes.
        self._ip_address = ip_address
        self._use_socket = use_socket
        self._socket_port = socket_port
        self._visa_backend = visa_backend
        self._resource = self._build_resource()
        self._waveform_chunk_size = 32768
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
        self._download_mode = "legacy"
        self._fast_options = {
            "poll_interval": 0.005,
            "trigger_timeout": 5.0,
            "waveform_delay": 0.01,
            "cache_vertical_settings": True,
            "arm_delay": 0.05,
            "require_trigger_state_change": True,
            "max_retries": 2,
            "min_vpp": None,
            "waveform_points_timeout": 0.5,
        }
        self._last_acquisition_attempts = 1

    def _build_resource(self):
        if self._use_socket:
            return f"TCPIP0::{self._ip_address}::{self._socket_port}::SOCKET"
        return f"TCPIP0::{self._ip_address}::INSTR"

    def setConnection(self, ip_address=None, use_socket=None, socket_port=None,
                      visa_backend=None):
        if ip_address is not None:
            self._ip_address = ip_address
        if use_socket is not None:
            self._use_socket = use_socket
        if socket_port is not None:
            self._socket_port = socket_port
        if visa_backend is not None:
            self._visa_backend = visa_backend
        self._resource = self._build_resource()
        return

    def _visaResourceManager(self):
        backend = self._visa_backend
        if backend in (None, "", "nivisa", "ni", "default"):
            return pyvisa.ResourceManager()
        if backend in ("pyvisa", "pyvisa-py", "@py"):
            return pyvisa.ResourceManager("@py")
        return pyvisa.ResourceManager(backend)

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
            t = 0
            v1 = 0
            v2m = 0
            return t, v1, v2m

        # Get Vertical values
        for i in tqdm(range(int(self._acquisition))):
            if i==0:
                v1, v2m = self.getchannels((1,),mdepth)
            else:
                v1aux, v2maux = self.getchannels((1,),mdepth)
                v1 = v1 + v1aux
                v2m = v2m + v2maux
        v1 = v1 / int(self._acquisition)
        v2m = v2m / int(self._acquisition)

        # Get Horizontal values
        t = self.getHorValues(mdepth)

        # Close communication
        self.closeComm()

        return t, v1, v2m

    ############################
    # Communication control
    ############################
    def initComm(self):
        resource_manager = self._visaResourceManager()
        self._osci = resource_manager.open_resource(self._resource)
        self._osci.timeout = 5000

        if self._use_socket:
            self._osci.read_termination = '\n'
            self._osci.write_termination = '\n'

        self._clearCommBuffer()
        self._osci.write(":WAV:FORM BYTE")
        self._osci.write(":WAV:MODE NORM")
        return

    def _clearCommBuffer(self):
        try:
            self._osci.clear()
        except (AttributeError, pyvisa.errors.VisaIOError):
            pass

        original_timeout = getattr(self._osci, "timeout", None)
        try:
            self._osci.timeout = 50
            for _ in range(20):
                try:
                    self._osci.read_bytes(4096, chunk_size=4096)
                except (AttributeError, pyvisa.errors.VisaIOError):
                    break
        finally:
            if original_timeout is not None:
                self._osci.timeout = original_timeout

    def closeComm(self):
        try:
            self._osci.close()
        except pyvisa.errors.VisaIOError as exc:
            print(f"Warning: VISA session did not close cleanly: {exc}")
        return

    def getID(self):
        return self._osci.query("*IDN?")

    def _queryText(self, command, retries=2, valid_values=None):
        last_response = ""
        last_error = None
        valid_upper = None
        if valid_values is not None:
            valid_upper = {value.upper() for value in valid_values}

        for attempt in range(retries + 1):
            try:
                response = self._osci.query(command).strip()
                last_response = response
                if valid_upper is None or response.upper() in valid_upper:
                    return response
            except (pyvisa.errors.VisaIOError, UnicodeDecodeError) as exc:
                last_error = exc

            self._clearCommBuffer()

        if last_error is not None:
            raise RuntimeError(f"Rigol query failed for {command}: {last_error}")
        raise ValueError(f"Unexpected Rigol response for {command}: {last_response!r}")

    def _queryFloat(self, command, retries=2):
        last_response = ""
        last_error = None
        for _ in range(retries + 1):
            try:
                response = self._queryText(command, retries=0)
                last_response = response
                return float(response)
            except (ValueError, RuntimeError) as exc:
                last_error = exc
                self._clearCommBuffer()

        raise ValueError(
            f"Could not parse Rigol numeric response for {command}: "
            f"{last_response!r}"
        ) from last_error

    ############################
    # Configuration
    ############################
    def config(self, channels=(1,), chanBand=('OFF',), chanCoup=('AC',),
               chanInv=('OFF',), chanImp = ('OMEG',),
               trigSource='CHAN1', trigCoup='AC', trigLevel=0.0, trigSlope = 'POS',
               acquisition=1,mdepth=14000, download_mode=None,
               poll_interval=None, trigger_timeout=None, waveform_delay=None,
               cache_vertical_settings=None, arm_delay=None,
               require_trigger_state_change=None, max_retries=None,
               min_vpp=None, waveform_points_timeout=None):

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
        if download_mode is not None:
            self._download_mode = download_mode.lower()
        fast_options = {
            "poll_interval": poll_interval,
            "trigger_timeout": trigger_timeout,
            "waveform_delay": waveform_delay,
            "cache_vertical_settings": cache_vertical_settings,
            "arm_delay": arm_delay,
            "require_trigger_state_change": require_trigger_state_change,
            "max_retries": max_retries,
            "min_vpp": min_vpp,
            "waveform_points_timeout": waveform_points_timeout,
        }
        for key, value in fast_options.items():
            if value is not None:
                self._fast_options[key] = value
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
        return

    def setandcheckmdepth(self,mdepth):
        self._osci.write(f":ACQ:MDEP {int(mdepth)}")
        mdepthread = self._queryText(":ACQ:MDEP?")
        if int(mdepthread) != int(mdepth):
            print("The requested memory depth is incorrect.")
            return 1
        else:
            return 0

    def setPeakAcquisition(self):
        self._osci.write(":ACQ:TYPE PEAK")
        return

    def setAvgAcquisition(self, nAvg=16):
        self._osci.write(":ACQ:TYPE AVER")
        self._osci.write(f":ACQ:AVER {int(nAvg)}")
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
        hscale = self._queryFloat(":TIMebase:SCALe?")
        hoffset = self._queryFloat(":TIMebase:OFFSet?")
        Srate = self._queryFloat(":ACQuire:SRATe?")
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
        return self._queryFloat(f":CHAN{channel}:SCAL?")

    def getVertOffset(self, channel):
        return self._queryFloat(f":CHAN{channel}:OFFS?")

    def _getVMaxOrNan(self, channel):
        try:
            return self.getVMax(channel)
        except (RuntimeError, ValueError, pyvisa.errors.VisaIOError,
                UnicodeDecodeError) as exc:
            print(f"Warning: could not read VMAX for channel {channel}: {exc}")
            self._clearCommBuffer()
            return float("nan")

    def _queryWaveformData(self, expected_points=None):
        kwargs = {
            "datatype": 'B',
            "container": np.array,
            "chunk_size": self._waveform_chunk_size,
        }
        original_chunk_size = getattr(self._osci, "chunk_size", None)

        if expected_points is not None:
            kwargs["data_points"] = int(expected_points)

        try:
            return self._osci.query_binary_values(":WAV:DATA?",
                                                  expect_termination=False,
                                                  **kwargs)
        except TypeError:
            if expected_points is not None and original_chunk_size is not None:
                self._osci.chunk_size = self._waveform_chunk_size
            try:
                return self._osci.query_binary_values(":WAV:DATA?",
                                                      datatype='B',
                                                      container=np.array)
            finally:
                if original_chunk_size is not None:
                    self._osci.chunk_size = original_chunk_size
        except (pyvisa.errors.VisaIOError, UnicodeDecodeError) as exc:
            self._clearCommBuffer()
            raise RuntimeError(
                f"Rigol waveform binary read failed and the VISA buffer was cleared: {exc}"
            ) from exc

    def _rawWaveformToVolts(self, raw, channel, vscale=None, offset=None):
        # Convert Rigol BYTE waveform data to volts using the same calibration
        # convention used by the legacy download path.
        values = np.array(raw)
        if vscale is None:
            vscale = self.getVertScale(channel)
        if offset is None:
            offset = self.getVertOffset(channel)
        ref = 127.0
        div = 25.4
        return (values*1.0 - ref)/div * vscale - offset

    def _checkRawWaveformSaturation(self, raw, lower_limit=1, upper_limit=254,
                                    min_count=2):
        raw = np.asarray(raw)
        if raw.size == 0:
            return False, False, 0, 0

        # Values below/above the safe ADC range indicate clipping. Requiring
        # more than one point avoids reacting to a single isolated spike.
        lower_count = int(np.count_nonzero(raw < lower_limit))
        upper_count = int(np.count_nonzero(raw > upper_limit))
        lower_saturated = lower_count >= min_count
        upper_saturated = upper_count >= min_count
        return lower_saturated, upper_saturated, lower_count, upper_count

    def _readRawWaveformFast(self, channel, mem_depth, delay_time=0.0,
                             waveform_timeout=5.0,
                             waveform_poll_interval=0.005,
                             waveform_points_timeout=0.5):
        # Configure a RAW waveform read from internal memory. This helper only
        # downloads bytes; voltage conversion is kept separate for reuse.
        self._osci.write(f":WAV:SOUR CHAN{channel}")
        self._osci.write(":WAV:FORM BYTE")
        self._osci.write(":WAV:MODE RAW")
        self._osci.write(f":WAV:POIN {int(mem_depth)}")
        self._osci.write(":WAV:STAR 1")
        self._osci.write(f":WAV:STOP {int(mem_depth)}")
        self._osci.write(":WAV:RES")
        self._osci.write(":WAV:BEG")
        if delay_time > 0:
            time.sleep(delay_time)

        # Wait until the Rigol waveform-reading thread has filled the buffer
        # with the requested number of internal-memory points.
        waveform_status = self.waitForWaveformRead(
            timeout_s=waveform_timeout,
            poll_interval=waveform_poll_interval,
            expected_points=mem_depth,
            points_timeout_s=waveform_points_timeout,
        )
        try:
            available_points = int(waveform_status.split(",", 1)[1])
        except (IndexError, ValueError):
            available_points = 0
        if 0 < available_points < int(mem_depth):
            raise RuntimeError(
                f"Rigol reports only {available_points} waveform points "
                f"available, expected {int(mem_depth)}."
            )

        read_ok = False
        try:
            # The binary query blocks until PyVISA has received the block.
            raw = self._queryWaveformData(expected_points=mem_depth)
            read_ok = True
        finally:
            if not read_ok:
                self._clearCommBuffer()
            try:
                self._osci.write(":WAV:END")
            except pyvisa.errors.VisaIOError as exc:
                print(f"Warning: could not send :WAV:END cleanly: {exc}")
                self._clearCommBuffer()

        raw = np.array(raw)
        if raw.size == 0:
            raise RuntimeError(
                "Rigol returned 0 waveform points after :WAV:STAT? reported IDLE."
            )
        if raw.size != int(mem_depth):
            raise RuntimeError(
                f"Rigol returned {raw.size} waveform points, "
                f"expected {int(mem_depth)}."
            )
        return raw

    def getVertValues(self, channel, mem_depth, delay_time=0.5):
        self._osci.write(f":WAV:SOUR CHAN{channel}")
        self._osci.write(":WAV:FORM BYTE")
        self._osci.write(":WAV:MODE RAW")
        self._osci.write(f":WAV:POIN {int(mem_depth)}")
        self._osci.write(f":WAV:STAR 1") # preamble in bits 0-10
        self._osci.write(f":WAV:STOP {int(mem_depth)}")
        self._osci.write(":WAV:RES")
        self._osci.write(":WAV:BEG")
        time.sleep(delay_time)

        raw = self._queryWaveformData(expected_points=mem_depth)
        time.sleep(0.2)
        # IMPORTANT: The vertical axis has 10 divisions,
        #            but only 8 are visible on the screen.
        return self._rawWaveformToVolts(raw, channel)

    def getVertValuesFast(self, channel, mem_depth, delay_time=0.0,
                          vscale=None, offset=None,
                          waveform_timeout=5.0,
                          waveform_poll_interval=0.005,
                          waveform_points_timeout=0.5):
        raw = self._readRawWaveformFast(
            channel,
            mem_depth,
            delay_time=delay_time,
            waveform_timeout=waveform_timeout,
            waveform_poll_interval=waveform_poll_interval,
            waveform_points_timeout=waveform_points_timeout,
        )
        return self._rawWaveformToVolts(raw, channel, vscale=vscale, offset=offset)

    def waitForWaveformRead(self, timeout_s=5.0, poll_interval=0.005,
                            expected_points=None, points_timeout_s=0.5):
        start = time.perf_counter()
        idle_start = None
        last_status = ""
        while True:
            last_status = self._queryText(":WAV:STAT?").upper()
            state = last_status.split(",", 1)[0]
            if state == "IDLE":
                if expected_points is None:
                    return last_status
                try:
                    available_points = int(last_status.split(",", 1)[1])
                except (IndexError, ValueError):
                    available_points = 0
                if available_points >= int(expected_points):
                    return last_status
                if idle_start is None:
                    idle_start = time.perf_counter()
                if (time.perf_counter() - idle_start) >= points_timeout_s:
                    return last_status
            else:
                idle_start = None
            if timeout_s is not None and (time.perf_counter() - start) > timeout_s:
                raise TimeoutError(
                    f"Timeout waiting for Rigol waveform read. Last status: {last_status}"
                )
            time.sleep(poll_interval)

    def waitForSingleTrigger(self, timeout_s=5.0, poll_interval=0.005,
                             arm_delay=0.05, require_state_change=True):
        if arm_delay > 0:
            time.sleep(arm_delay)

        start = time.perf_counter()
        saw_running_state = (arm_delay > 0) or (not require_state_change)
        last_status = ""
        while True:
            last_status = self._queryText(
                ":TRIGger:STATus?",
                valid_values=("TD", "WAIT", "RUN", "AUTO", "STOP"),
            ).upper()
            if last_status != "STOP":
                saw_running_state = True
            if last_status == "STOP" and saw_running_state:
                return last_status
            if timeout_s is not None and (time.perf_counter() - start) > timeout_s:
                raise TimeoutError(
                    f"Timeout waiting for Rigol single trigger. Last status: {last_status}"
                )
            time.sleep(poll_interval)

    def getchannels(self, channels, mdepth):
        if self._download_mode in ("fast", "single", "optimized"):
            return self.getchannelsFast(channels, mdepth, **self._fast_options)

        self._last_acquisition_attempts = 1
        self.run()
        time.sleep(0.5)
        self.stop()
        for i in range(len(channels)):
            if i == 0:
                MV = self.getVertValues(channels[i], mdepth)
            else:
                MV = np.vstack((MV, self.getVertValues(channels[i], mdepth)))

        # Get the maximum value of channel 2
        V2MAX = self._getVMaxOrNan(2)
        self.run()
        return MV, V2MAX

    def getchannelsFast(self, channels, mdepth, poll_interval=0.005,
                        trigger_timeout=5.0, waveform_delay=0.01,
                        cache_vertical_settings=True, arm_delay=0.05,
                        require_trigger_state_change=True, max_retries=2,
                        min_vpp=None, waveform_points_timeout=0.5):
        last_error = None
        for attempt in range(max_retries + 1):
            self._last_acquisition_attempts = attempt + 1
            try:
                self._osci.write(":SINGle")
                self.waitForSingleTrigger(
                    timeout_s=trigger_timeout,
                    poll_interval=poll_interval,
                    arm_delay=arm_delay,
                    require_state_change=require_trigger_state_change,
                )

                if cache_vertical_settings:
                    vertical_settings = {
                        channel: (self.getVertScale(channel), self.getVertOffset(channel))
                        for channel in channels
                    }
                else:
                    vertical_settings = {}

                for i, channel in enumerate(channels):
                    vscale, offset = vertical_settings.get(channel, (None, None))
                    values = self.getVertValuesFast(
                        channel,
                        mdepth,
                        delay_time=waveform_delay,
                        vscale=vscale,
                        offset=offset,
                        waveform_timeout=trigger_timeout,
                        waveform_poll_interval=poll_interval,
                        waveform_points_timeout=waveform_points_timeout,
                    )
                    if i == 0:
                        MV = values
                    else:
                        MV = np.vstack((MV, values))

                if min_vpp is not None:
                    measured_vpp = np.ptp(MV, axis=-1)
                    if np.max(measured_vpp) < min_vpp:
                        raise RuntimeError(
                            f"Captured waveform Vpp {np.max(measured_vpp):.4g} V "
                            f"is below min_vpp {min_vpp:.4g} V."
                        )

                V2MAX = self._getVMaxOrNan(2)
                return MV, V2MAX
            except (RuntimeError, TimeoutError, pyvisa.errors.VisaIOError,
                    UnicodeDecodeError, ValueError) as exc:
                last_error = exc
                self._clearCommBuffer()
                if attempt >= max_retries:
                    raise

        raise RuntimeError(f"Rigol fast acquisition failed: {last_error}")

    def getVMax(self, channel):
        vmax = self._queryFloat(f":MEASure:VMAX? CHANnel{channel}")
        return vmax

    def getVMin(self, channel):
        vmin = self._queryFloat(f":MEASure:VMIN? CHANnel{channel}")
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

    def _safe_get_vmin_vmax(self, channel, invalid_threshold=1e30):
        vmin = self.getVMin(channel)
        vmax = self.getVMax(channel)

        invalid_min = self._is_invalid_measurement(vmin, invalid_threshold)
        invalid_max = self._is_invalid_measurement(vmax, invalid_threshold)

        return vmin, vmax, invalid_min, invalid_max

    def _getRawMinMaxFast(self, channel, mem_depth, vscale=None, offset=None,
                          settle_wait=0.0, invalid_threshold=1e30,
                          saturation_min_count=2):
        last_error = None
        max_retries = self._fast_options["max_retries"]
        for attempt in range(max_retries + 1):
            try:
                # Arm a single acquisition so min/max are calculated from a
                # fresh triggered waveform, not from a previous screen state.
                self._osci.write(":SINGle")
                self.waitForSingleTrigger(
                    timeout_s=self._fast_options["trigger_timeout"],
                    poll_interval=self._fast_options["poll_interval"],
                    arm_delay=self._fast_options["arm_delay"],
                    require_state_change=self._fast_options[
                        "require_trigger_state_change"
                    ],
                )
                if settle_wait > 0:
                    time.sleep(settle_wait)

                raw = self._readRawWaveformFast(
                    channel,
                    mem_depth,
                    delay_time=self._fast_options["waveform_delay"],
                    waveform_timeout=self._fast_options["trigger_timeout"],
                    waveform_poll_interval=self._fast_options["poll_interval"],
                    waveform_points_timeout=self._fast_options[
                        "waveform_points_timeout"
                    ],
                )
                # Compute min/max locally on the same RAW data path used for
                # the final optimized measurement.
                values = self._rawWaveformToVolts(
                    raw,
                    channel,
                    vscale=vscale,
                    offset=offset,
                )
                vmin = float(np.min(values))
                vmax = float(np.max(values))
                (
                    lower_saturated,
                    upper_saturated,
                    lower_count,
                    upper_count,
                ) = self._checkRawWaveformSaturation(
                    raw,
                    min_count=saturation_min_count,
                )
                invalid_min = (
                    self._is_invalid_measurement(vmin, invalid_threshold)
                    or lower_saturated
                )
                invalid_max = (
                    self._is_invalid_measurement(vmax, invalid_threshold)
                    or upper_saturated
                )
                return (
                    vmin,
                    vmax,
                    invalid_min,
                    invalid_max,
                    lower_saturated,
                    upper_saturated,
                    lower_count,
                    upper_count,
                )
            except (RuntimeError, TimeoutError, pyvisa.errors.VisaIOError,
                    UnicodeDecodeError, ValueError) as exc:
                last_error = exc
                self._clearCommBuffer()
                if attempt >= max_retries:
                    raise

        raise RuntimeError(f"Rigol raw min/max acquisition failed: {last_error}")

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
        minmax_source="measure",
        saturation_min_count=2,
        verbose=True
    ):
        """
        Autoajuste condicional de escala vertical y offset.

        La función:
        - obtiene VMAX/VMIN con mediciones internas o con RAW single;
        - calcula cuántas divisiones verticales ocupa la señal;
        - reajusta la escala solo si es necesario;
        - detecta saturación RAW si se usa minmax_source='raw';
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
            - acq_wait: tiempo de espera para adquirir señal en modo 'measure'.
            - settle_wait: tiempo de estabilización antes de calcular min/max.
            - minmax_source: 'measure' usa :MEASure; 'raw' usa single+RAW.
            - saturation_min_count: cantidad minima de bytes RAW saturados.
            - verbose: si True imprime información detallada.
        """

        # Si no se especifican canales usar los definidos en config()
        if channels is None:
            channels = self._channels
        minmax_source = minmax_source.lower()
        if minmax_source not in ("measure", "raw", "raw_fast"):
            raise ValueError("Usar minmax_source='measure' o minmax_source='raw'.")

        # Init communication
        self.initComm()

        # Re-apply the configured trigger before auto-adjust acquisitions.
        # This avoids inheriting trigger state from previous captures.
        self.setEdgeTrigger(
            self._trigSource,
            self._trigSlope,
            self._trigCoup,
            self._trigLevel,
        )

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

        # Procesar cada canal
        for ch in channels:

            adjusted[ch] = False

            # Iteraciones de ajuste si la señal está inicialmente fuera de rango
            for it in range(n_iter):
                # Configuración actual del canal
                current_scale = self.getVertScale(ch)
                current_offset = self.getVertOffset(ch)

                if minmax_source == "measure":
                    # Historical path: use the Rigol measurement engine after
                    # a RUN/STOP capture.
                    self.run()
                    time.sleep(acq_wait)
                    self.stop()
                    time.sleep(settle_wait)
                    vmin, vmax, invalid_min, invalid_max = self._safe_get_vmin_vmax(
                        ch,
                        invalid_threshold=invalid_threshold,
                    )
                    lower_saturated = False
                    upper_saturated = False
                    lower_count = 0
                    upper_count = 0
                else:
                    # Optimized path: use single-trigger RAW data and compute
                    # min/max locally from the downloaded memory points.
                    (
                        vmin,
                        vmax,
                        invalid_min,
                        invalid_max,
                        lower_saturated,
                        upper_saturated,
                        lower_count,
                        upper_count,
                    ) = self._getRawMinMaxFast(
                        ch,
                        self._mdepth,
                        vscale=current_scale,
                        offset=current_offset,
                        settle_wait=settle_wait,
                        invalid_threshold=invalid_threshold,
                        saturation_min_count=saturation_min_count,
                    )

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
                        if minmax_source == "measure":
                            print(
                                f"CH{ch}: medición fuera de rango "
                                f"(Vmin={vmin:.4g}, Vmax={vmax:.4g})"
                            )
                        else:
                            print(
                                f"CH{ch}: RAW saturada/fuera de rango "
                                f"(Vmin={vmin:.4g}, Vmax={vmax:.4g}, "
                                f"sat_low={lower_saturated}, "
                                f"sat_high={upper_saturated}, "
                                f"n_low={lower_count}, "
                                f"n_high={upper_count})"
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

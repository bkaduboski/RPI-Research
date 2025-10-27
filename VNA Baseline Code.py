from pymeasure.instruments import Instrument
import numpy as np
import csv
import time
import matplotlib.pyplot as plt


class KeysightE5080B(Instrument):
    """Enhanced PyMeasure driver for Keysight E5080B ENA Series VNA."""

    def __init__(self, resource_name):
        super().__init__(resource_name, "Keysight E5080B VNA")
        if hasattr(self.adapter, "connection"):
            self.adapter.connection.timeout = 10000  # 10 s timeout for long sweeps
        self.write(":FORM:DATA ASCII")  # ensure ASCII data for parsing

    # --- Setup functions ---
    def preset(self):
        """Preset instrument to factory defaults."""
        self.write(":SYST:PRES")

    def set_frequency_range(self, start, stop):
        self.write(f":SENS1:FREQ:STAR {start}")
        self.write(f":SENS1:FREQ:STOP {stop}")

    def set_points(self, points):
        self.write(f":SENS1:SWE:POIN {points}")

    def set_power(self, power_dbm):
        self.write(f":SOUR1:POW {power_dbm}")

    def set_if_bandwidth(self, bw):
        self.write(f":SENS1:BWID {bw}")

    def select_measurement(self, sparam="S21"):
        """Select or create an S-parameter measurement (e.g., S21, S11)."""
        self.write(f":CALC1:PAR:DEF 'Meas1',{sparam}")
        self.write(":DISP:WIND1:TRAC1:FEED 'Meas1'")
        self.write(":CALC1:PAR:SEL 'Meas1'")

    def load_calibration(self, filepath):
        """Load a stored correction/calibration file."""
        try:
            self.write(f':MMEM:LOAD:CORR "{filepath}"')
            time.sleep(2)  # Allow time for calibration load
        except Exception as e:
            raise RuntimeError(f"Failed to load calibration file: {e}")

    def set_single_sweep(self):
        """Ensure VNA is in single-sweep mode."""
        self.write(":INIT1:CONT OFF")

    def trigger_sweep(self):
        """Trigger single sweep and wait for completion."""
        self.write(":INIT1:IMM")
        self.ask("*OPC?")  # Wait until operation completes

    def fetch_sdata(self):
        """Fetch complex S-parameter data as complex NumPy array."""
        raw = np.array(self.values(":CALC1:DATA? SDATA"), dtype=float)
        if len(raw) < 2:
            raise RuntimeError("Incomplete data returned from VNA.")
        re, im = raw[::2], raw[1::2]
        return re + 1j * im

    def check_errors(self):
        """Query system error queue."""
        err = self.ask(":SYST:ERR?")
        if not err.strip().startswith("0"):
            print(f"⚠️ Instrument Error: {err.strip()}")

    def shutdown(self):
        """Safely close VISA connection."""
        try:
            if hasattr(self.adapter, "connection"):
                self.adapter.connection.close()
        except Exception:
            pass


# --- USER SETTINGS ---
VNA_ADDRESS = "TCPIP0::192.168.0.5::inst0::INSTR"
START_FREQ = 1e9       # Hz
STOP_FREQ = 10e9       # Hz
POINTS = 1601
POWER = -5             # dBm
IF_BW = 1e3            # Hz
FIELDS = np.linspace(0.05, 0.30, 6)  # Tesla (dummy field values)
CAL_FILE = "FMR_calibration.corr"
OUTPUT_CSV = "FMR_pymeasure_results.csv"


# --- MAIN SCRIPT ---
print("Connecting to VNA...")
vna = None

try:
    vna = KeysightE5080B(VNA_ADDRESS)
    idn = vna.ask("*IDN?")
    print("Connected to:", idn.strip())

    print("\nPresetting and configuring VNA...")
    vna.preset()
    time.sleep(5)

    vna.set_frequency_range(START_FREQ, STOP_FREQ)
    vna.set_points(POINTS)
    vna.set_power(POWER)
    vna.set_if_bandwidth(IF_BW)
    vna.select_measurement("S21")
    vna.set_single_sweep()

    # Load calibration (optional)
    try:
        vna.load_calibration(CAL_FILE)
        print(f"Calibration '{CAL_FILE}' loaded successfully.")
    except Exception as e:
        print(f"⚠️ Warning: calibration load skipped ({e}).")

    vna.check_errors()

    freqs = np.linspace(START_FREQ, STOP_FREQ, POINTS)
    results = {}

    def set_magnet_field(field):
        """Placeholder for magnet control — replace with actual hardware call."""
        print(f"Setting field to {field:.3f} T...")
        time.sleep(1)

    print("\nStarting field sweeps...\n")
    for field in FIELDS:
        set_magnet_field(field)
        vna.trigger_sweep()
        trace = vna.fetch_sdata()
        results[field] = trace
        print(f"✓ Sweep complete for {field:.3f} T")

    print("\nAll sweeps complete.")

    # ===========================================================
    # --- PLOT RESULTS ---
    # ===========================================================
    plt.figure(figsize=(8, 5))
    for field, data in results.items():
        mag_db = 20 * np.log10(np.abs(data) + 1e-12)
        plt.plot(freqs / 1e9, mag_db, label=f"{field:.2f} T")
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("|S21| (dB)")
    plt.title("FMR Sweeps (PyMeasure + Keysight E5080B)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

    # ===========================================================
    # --- SAVE DATA ---
    # ===========================================================
    print(f"\nSaving data to '{OUTPUT_CSV}'...")
    assert all(len(trace) == len(freqs) for trace in results.values()), "Trace length mismatch!"

    mag_db_matrix = np.column_stack([
        20 * np.log10(np.abs(results[field]) + 1e-12) for field in FIELDS
    ])
    data_to_save = np.column_stack([freqs, mag_db_matrix])

    header = ["Frequency (Hz)"] + [f"S21_mag_dB_H{field:.3f}T" for field in FIELDS]
    with open(OUTPUT_CSV, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["# Keysight E5080B Sweep Data"])
        writer.writerow([f"# Freq range: {START_FREQ/1e9:.3f}-{STOP_FREQ/1e9:.3f} GHz"])
        writer.writerow([f"# Points: {POINTS}, Power: {POWER} dBm, IF BW: {IF_BW} Hz"])
        writer.writerow([f"# Calibration: {CAL_FILE}"])
        writer.writerow([])
        writer.writerow(header)
        writer.writerows(data_to_save)

    print("✅ Data saved successfully!")

except Exception as e:
    print(f"❌ Error during VNA operation: {e}")

finally:
    if vna is not None:
        vna.shutdown()
        print("VNA connection closed (cleanup).")
    plt.close("all")

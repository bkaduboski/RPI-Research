import pyvisa
import time
import threading
import csv
import os
import matplotlib.pyplot as plt
import numpy as np

# === CONFIGURATION ===
save_folder = r"C:\Users\Brendan\Documents\lab\dataset"
os.makedirs(save_folder, exist_ok=True)

csv_filename = os.path.join(save_folder, "sr865_data.csv")
plot_r_filename = os.path.join(save_folder, "sr865_plot.png")
plot_theta_filename = os.path.join(save_folder, "sr865_theta_plot.png")
fft_plot_filename = os.path.join(save_folder, "sr865_fft_plot.png")
fft_csv_filename = os.path.join(save_folder, "sr865_fft_data.csv")

sampling_interval = 0.2  # seconds
duration = 14000         # total duration in seconds

# === FLAGS ===
stop_flag = False
marker_times = []
set_times = []
marker_lock = threading.Lock()

# === Input thread ===
def monitor_input():
    global stop_flag
    while not stop_flag:
        user_input = input().strip().lower()
        current_t = time.time() - start_time

        if user_input == 'm':
            with marker_lock:
                marker_times.append(current_t)
            print(f"🔖 Marker (m) added at {current_t:.2f}s")
        elif user_input == 'n':
            with marker_lock:
                set_times.append(current_t)
            print(f"📍 Set (n) added at {current_t:.2f}s")
        elif user_input == '':
            stop_flag = True
            print("🛑 Stopping early...")

threading.Thread(target=monitor_input, daemon=True).start()

# === CSV Setup ===
with open(csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["t (s)", "X (uV)", "Y (uV)", "R (uV)", "Theta (deg)", "Note"])

# === Connect to SR865 ===
rm = pyvisa.ResourceManager()
sr865 = rm.open_resource("USB0::0xB506::0x2000::004198::INSTR")
print("Connected to:", sr865.query("*IDN?").strip())
print("Type 'm' + Enter to mark a field switch, 'n' + Enter for a SET point, or just Enter to stop.\n")

# === Data Storage ===
t_values = []
r_values = []
theta_values = []

# === Measurement Loop ===
start_time = time.time()

while not stop_flag:
    current_time = time.time() - start_time
    if current_time > duration:
        break

    try:
        x = float(sr865.query("OUTP? 0")) * 1e6
        y = float(sr865.query("OUTP? 1")) * 1e6
        r = float(sr865.query("OUTP? 2")) * 1e6
        theta = float(sr865.query("OUTP? 3"))

        t_values.append(current_time)
        r_values.append(r)
        theta_values.append(theta)

        with open(csv_filename, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([f"{current_time:.5f}", f"{x:.5f}", f"{y:.5f}", f"{r:.5f}", f"{theta:.5f}", ""])

        print(f"t = {current_time:6.2f}s | X = {x:.2f} uV, Y = {y:.2f} uV → R = {r:.2f} uV, θ = {theta:.2f}°")

    except Exception as e:
        print("Read error:", e)

    time.sleep(sampling_interval)

# === Handle Markers ===
with open(csv_filename, mode='a', newline='') as file:
    writer = csv.writer(file)
    for mark_time in marker_times:
        writer.writerow([f"{mark_time:.5f}", "", "", "", "", "MARK"])
    for set_time in set_times:
        writer.writerow([f"{set_time:.5f}", "", "", "", "", "SET"])

# === Cleanup ===
sr865.close()
print("\n✅ Logging stopped. Data saved to CSV.")

# === Plot R vs t ===
plt.figure(figsize=(10, 5))
plt.plot(t_values, r_values, label="R (uV)", linestyle='-', marker='o', markersize=2)
for mark_time in marker_times:
    plt.axvline(x=mark_time, color='red', linestyle='--', alpha=0.6, label='MARK' if mark_time == marker_times[0] else "")
for set_time in set_times:
    plt.axvline(x=set_time, color='blue', linestyle=':', alpha=0.6, label='SET' if set_time == set_times[0] else "")
plt.title("R over Time")
plt.xlabel("Time (s)")
plt.ylabel("R (uV)")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(plot_r_filename)
plt.show()

# === Plot Theta vs t ===
plt.figure(figsize=(10, 5))
plt.plot(t_values, theta_values, label="Theta (deg)", linestyle='-', marker='x', color='orange', markersize=2)
for mark_time in marker_times:
    plt.axvline(x=mark_time, color='red', linestyle='--', alpha=0.6, label='MARK' if mark_time == marker_times[0] else "")
for set_time in set_times:
    plt.axvline(x=set_time, color='blue', linestyle=':', alpha=0.6, label='SET' if set_time == set_times[0] else "")
plt.title("Theta over Time")
plt.xlabel("Time (s)")
plt.ylabel("Theta (°)")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(plot_theta_filename)
#plt.show()

# === FFT of R ===

r_array = np.array(r_values)
n = len(r_array)
r_fft = np.fft.fft(r_array)
freqs = np.fft.fftfreq(n, d=sampling_interval)
pos_freqs = freqs[:n // 2]
magnitude = np.abs(r_fft[:n // 2])

with open(fft_csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Frequency (Hz)", "Magnitude"])
    for f, m in zip(pos_freqs, magnitude):
        writer.writerow([f, m])
plt.figure(figsize=(10, 5))
plt.plot(pos_freqs, magnitude, color='purple')
plt.title("FFT of R")
plt.xlabel("Frequency (Hz)")
plt.ylabel("Magnitude")
plt.grid(True)
plt.tight_layout()
plt.savefig(fft_plot_filename)
#plt.show()
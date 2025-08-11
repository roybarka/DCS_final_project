import serial
import threading
import time
import math
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# -------- מבנה הנתונים --------
angle_distance_data = [None] * 180
angle_Light_data = [None] * 180


# -------- מחלקת בקר --------
class MSPController:
    def __init__(self, port, baudrate=9600):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)
        print(f"Connected to {port} at {baudrate} baud.")

    def read_data(self):
        data = self.ser.readline().decode(errors="ignore").strip()
        return data if data else None

    def send_command(self, command):
        self.ser.write(command.encode())
        print(f"Command '{command}' sent to controller.")

    def close(self):
        self.ser.close()

# -------- Thread לקריאת הנתונים --------
def listen_for_controller_Dist(controller, stop_event):
    buffer_angle = None
    buffer_vals = []
    max_samples = 10
    tolerance_cm = 4  # within ±3 cm counts as same cluster

    def choose_best_cluster(readings):
        # Build clusters of close readings
        clusters = []
        for val in readings:
            cluster = [x for x in readings if abs(x - val) <= tolerance_cm]
            clusters.append(cluster)
        # Pick largest cluster; if tie, pick smallest spread
        best_cluster = max(clusters, key=lambda c: (len(c), -(max(c) - min(c))))
        return round(sum(best_cluster) / len(best_cluster), 1)

    def process_angle(angle, readings):
        if not readings:
            return
        final_val = choose_best_cluster(readings)
        angle_distance_data[angle] = final_val
        print(f"Angle {angle}° = {final_val:.1f} cm (from {readings})")

    while not stop_event.is_set():
        data = controller.read_data()
        if not data:
            continue

        try:
            angle_str, dist_str = data.split(":")
            angle = int(angle_str)
            distance_us = int(dist_str)
            distance_cm = distance_us / 58.0

            if distance_cm == 0:  # ignore bad reading
                continue

        except ValueError:
            continue

        if not (0 <= angle < 180):
            continue

        if buffer_angle is None:
            # First reading in a batch
            buffer_angle = angle
            buffer_vals = [distance_cm]
        elif angle != buffer_angle:
            # New angle arrived before batch complete → process current
            process_angle(buffer_angle, buffer_vals)
            # Start new batch
            buffer_angle = angle
            buffer_vals = [distance_cm]
        else:
            # Same angle
            buffer_vals.append(distance_cm)
            if len(buffer_vals) >= max_samples:
                process_angle(buffer_angle, buffer_vals)
                buffer_angle = None
                buffer_vals = []

    # Flush leftover readings if thread exits
    if buffer_angle is not None and buffer_vals:
        process_angle(buffer_angle, buffer_vals)


def listen_for_controller_Object_and_Light(controller, stop_event):
    while not stop_event.is_set():
        data = controller.read_data()
        if data:
            try:
                angle_str,dist_str, Light_str = data.split(":")
                angle_raw = int(angle_str)
                distance_us = int(dist_str)
                distance = distance_us // 58.0
                Light_Power = float(Light_str)
                Light_Power = 100 *(Light_Power/1023)

                if 0 <= angle_raw < 180:
                    angle_Light_data[angle_raw] = Light_Power
                    print(f"Angle {angle_raw}° : Distance {distance} : {Light_Power}% Light Power ")

            except ValueError:
                continue

def listen_for_controller_Light(controller, stop_event):
     while not stop_event.is_set():
            data = controller.read_data()
            if data:
                try:
                    angle_str, Light_str = data.split(":")
                    angle_raw = int(angle_str)
                    Light_Power = float(Light_str)
                    Light_Power = 100 *(Light_Power/1023)
                    if 0 <= angle_raw < 180:
                        angle_Light_data[angle_raw] = Light_Power
                        print(f"Angle {angle_raw}° = {Light_Power}% Light Power ")

                except ValueError:
                    continue

# -------- Thread לגרף בר בתוך tkinter --------
def debug_bar_plot_thread_tk(root, stop_event):
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.set_ylim(0, 250)
    ax.set_xlim(0, 180)
    bars = ax.bar(range(180), [0]*180, width=1.0, color='skyblue')
    ax.set_xlabel("Angle [deg]")
    ax.set_ylabel("Distance [cm]")
    ax.set_title("Live Distance Measurements")

    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack()
    canvas.draw()

    def update_plot():
        if stop_event.is_set():
            return
        values = [angle_distance_data[i] if angle_distance_data[i] is not None else 0 for i in range(180)]
        for i, bar in enumerate(bars):
            bar.set_height(values[i])
        canvas.draw()
        root.after(100, update_plot)

    update_plot()

def wait_for_exit_gui_and_send_8(controller, stop_event, title="Exit Mode"):
    root = tk.Tk()
    root.title(title)

    info = tk.Label(root, text="לחזור לתפריט (נשלח '8' ונעצור האזנה ו-GUI)")
    info.pack(padx=10, pady=10)

    def on_exit():
        try:
            controller.send_command('8')
        except Exception as e:
            print(f"Warning: couldn't send '8' ({e})")
        if stop_event is not None:
            stop_event.set()
        root.destroy()

    btn = tk.Button(root, text="יציאה מהמצב", command=on_exit)
    btn.pack(padx=10, pady=10)

    root.protocol("WM_DELETE_WINDOW", on_exit)
    root.mainloop()


def get_mode_from_user():
    print("\nSelect Mode:")
    print("1 - Sonar Object detector Mode")
    print("2 - Angle Motor Rotation")
    print("3 - LDR Light  Detector")
    print("4 - Object + Light detector")
    print("5 - Load Scripts")
    print("6 - Run Scripts")
    print("0 - Exit")
    mode = input("Enter mode number: ")
    return mode.strip()

# --- הפעלת מצב 1 (כולל טרדים ו־GUI) ---
def run_mode_1(controller):
    global angle_distance_data
    angle_distance_data = [None] * 180  # reset data

    controller.send_command('1')
    stop_event = threading.Event()

    # Thread – listener
    listener_thread = threading.Thread(
        target=listen_for_controller_Dist,
        args=(controller, stop_event),
        daemon=True
    )
    listener_thread.start()

    # Tkinter window
    root = tk.Tk()
    root.title("Mode 1 - Sonar View")

    # Matplotlib figure embedded in Tkinter
    fig = plt.Figure(figsize=(6, 6))
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_zero_location("E")  # Start at 0° on right side
    ax.set_theta_direction(1)  # Clockwise
    ax.set_thetamin(0)
    ax.set_thetamax(180)
    ax.set_rlim(0, 250)

    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # Exit button
    def on_exit():
        controller.send_command('8')
        stop_event.set()
        root.destroy()

    exit_button = tk.Button(root, text="Exit Mode 1", command=on_exit)
    exit_button.pack(pady=5)

    # Plot update function
    def update_plot():
        ax.clear()
        ax.set_theta_zero_location("E")  # Start at 0° on right side
        ax.set_theta_direction(1)  # Clockwise
        ax.set_thetamin(0)
        ax.set_thetamax(180)
        ax.set_rlim(0, 100)  # 1 meter display range

        distance_threshold = 100  # cm, max detection range
        min_cluster_size = 30
        meas_angle = 30  # beam width
        max_gap_cm = 10  # max distance jump inside a cluster

        angles_all = []
        distances_all = []
        clusters = []
        current_cluster = []

        for idx, dist in enumerate(angle_distance_data):
            if dist is not None:
                angle_rad = math.radians(idx)
                angles_all.append(angle_rad)
                distances_all.append(dist)

                if dist <= distance_threshold:
                    if current_cluster:
                        last_dist = current_cluster[-1][1]
                        if abs(dist - last_dist) > max_gap_cm:
                            # split cluster due to gap
                            if len(current_cluster) >= min_cluster_size:
                                clusters.append(current_cluster)
                            current_cluster = []
                    current_cluster.append((idx, dist))
                else:
                    if len(current_cluster) >= min_cluster_size:
                        clusters.append(current_cluster)
                    current_cluster = []
            else:
                if len(current_cluster) >= min_cluster_size:
                    clusters.append(current_cluster)
                current_cluster = []

        if len(current_cluster) >= min_cluster_size:
            clusters.append(current_cluster)

        # Plot all scan points in green
        ax.scatter(angles_all, distances_all, c='lime', s=10, label="Scan")

        for cluster in clusters:
            angle_idxs = [idx for idx, _ in cluster]
            dists = [d for _, d in cluster]

            # Trim beam edges (15° from each side)
            trim_points = int(meas_angle / 2)
            if len(cluster) > 2 * trim_points:
                angle_idxs = angle_idxs[trim_points:-trim_points]
                dists = dists[trim_points:-trim_points]
            else:
                continue  # skip if cluster too small after trimming

            if not angle_idxs:
                continue

            phi_center = sum(angle_idxs) / len(angle_idxs)
            phi_center_rad = math.radians(phi_center)
            p_mean = sum(dists) / len(dists)

            # Correct width calculation after trimming
            valid_width_deg = angle_idxs[-1] - angle_idxs[0]
            l_real = 2 * math.pi * p_mean * (valid_width_deg / 360)

            # Draw object arc
            arc_angles = [math.radians(a) for a in range(angle_idxs[0], angle_idxs[-1] + 1)]
            arc_r = [p_mean] * len(arc_angles)
            ax.plot(arc_angles, arc_r, c='red', linewidth=2)

            # Label object
            label = f"φ={int(phi_center)}°\np={int(p_mean)}cm\nl={int(l_real)}cm"
            ax.text(phi_center_rad, p_mean + 5, label, fontsize=7, ha='center', color='blue',
                    bbox=dict(facecolor='white', alpha=0.6, edgecolor='none', pad=1))

        canvas.draw()

        if not stop_event.is_set():
            root.after(200, update_plot)

    update_plot()
    root.mainloop()

    listener_thread.join(timeout=2.0)
    print("Exited Mode 1.")

# -------- main --------
def main():
    port = "COM9"  # עדכן את הפורט לפי הצורך
    controller = MSPController(port)

    while True:
        choice = get_mode_from_user()

        if choice == '0':
            print("Exiting program.")
            break

        if choice == '1':
            run_mode_1(controller)

        if choice == '2':
            controller.send_command('2')
            degree = input("Enter degree between 0-180: ")
            deg = int(degree)
            deg = 600 + deg * 10
            deg = str(deg)
            controller.send_command(degree + '\n')

            stop_event = threading.Event()
            # הפעלת טרד האזנה בלבד
            listener_thread = threading.Thread(target=listen_for_controller_Dist, args=(controller, stop_event))
            listener_thread.daemon = True
            listener_thread.start()

            print("Listening for data... use the GUI button to exit.")
            # חלון קטן: בלחיצה שולח '8' ומסמן stop_event
            wait_for_exit_gui_and_send_8(controller, stop_event, title="Mode 2 - LDR")

            # ה־stop_event סומן מתוך הכפתור; מחכים שה־listener ימות בצורה מסודרת
            listener_thread.join(timeout=2.0)
            print("Exited Mode 2.")

        if choice == '3':
            controller.send_command('3')
            stop_event = threading.Event()
            listener_thread = threading.Thread(target=listen_for_controller_Light, args=(controller, stop_event))
            listener_thread.daemon = True
            listener_thread.start()

            print("Listening for data... use the GUI button to exit.")
            # חלון קטן: בלחיצה שולח '8' ומסמן stop_event
            wait_for_exit_gui_and_send_8(controller, stop_event, title="Mode 3 - LDR")

            # ה־stop_event סומן מתוך הכפתור; מחכים שה־listener ימות בצורה מסודרת
            listener_thread.join(timeout=2.0)
            print("Exited Mode 3.")

        if choice == '4':
            controller.send_command('4')
            stop_event = threading.Event()
            listener_thread = threading.Thread(target=listen_for_controller_Object_and_Light, args=(controller, stop_event))
            listener_thread.daemon = True
            listener_thread.start()

            print("Listening for data... use the GUI button to exit.")
            # חלון קטן: בלחיצה שולח '8' ומסמן stop_event
            wait_for_exit_gui_and_send_8(controller, stop_event, title="Mode 4 - LDR + HyperSonic")

            # ה־stop_event סומן מתוך הכפתור; מחכים שה־listener ימות בצורה מסודרת
            listener_thread.join(timeout=2.0)
            print("Exited Mode 4.")



    controller.close()

if __name__ == "__main__":
    main()

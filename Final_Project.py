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
def listen_for_controller(controller, stop_event):
    while not stop_event.is_set():
        data = controller.read_data()
        if data:
            try:
                angle_str, dist_str = data.split(":")
                angle_raw = int(angle_str)
                distance_us = int(dist_str)
                distance = distance_us // 58.0
                if 0 <= angle_raw < 180:
                    angle_distance_data[angle_raw] = distance
                    print(f"Angle {angle_raw}° = {distance} cm")

                    # החלקת קצה חריג מול שכנים
                    if 2 <= angle_raw <= 179:
                        mid = angle_distance_data[angle_raw - 1]
                        left = angle_distance_data[angle_raw - 2]
                        right = angle_distance_data[angle_raw]
                        if left is not None and right is not None and mid is not None:
                            if (abs(mid - left) > 30) and (abs(mid - right) > 30):
                                angle_distance_data[angle_raw - 1] = (left + right) // 2
            except ValueError:
                continue

# -------- Thread ל-GUI פולאר --------
def sonar_gui(stop_event):
    plt.ion()
    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, polar=True)

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetamin(0)
    ax.set_thetamax(180)

    max_distance = 250
    distance_threshold = 50
    min_cluster_size = 10
    meas_angle = 15  # רוחב אלומה משוער (מעלות)

    while not stop_event.is_set():
        time.sleep(0.5)
        ax.clear()
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_thetamin(0)
        ax.set_thetamax(180)
        ax.set_rlim(0, max_distance)

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

        ax.scatter(angles_all, distances_all, c='lime', s=10, label="Scan")

        for cluster in clusters:
            angle_idxs = [idx for idx, _ in cluster]
            dists = [d for _, d in cluster]

            phi_center = sum(angle_idxs) / len(angle_idxs)
            phi_center_rad = math.radians(phi_center)
            p_mean = sum(dists) / len(dists)
            l_width_deg = angle_idxs[-1] - angle_idxs[0] + meas_angle  # הכללת רוחב האלומה
            l_real = 2 * math.pi * p_mean * (l_width_deg / 360)       # קשת בקירוב

            angles_rad = [math.radians(a) for a in angle_idxs]
            ax.scatter(angles_rad, dists, c='red', s=30)

            label = f"φ={int(phi_center)}°\np={int(p_mean)}cm\nl={int(l_real)}cm"
            ax.text(phi_center_rad, p_mean + 10, label, fontsize=7, ha='center', color='blue',
                    bbox=dict(facecolor='white', alpha=0.6, edgecolor='none', pad=1))

        ax.set_title("Detected Objects: φ (deg), p (cm), l (cm)")
        plt.draw()
        plt.pause(0.001)

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
    angle_distance_data = [None] * 180  # איפוס תצוגה ישנה

    # שליחת פקודת מצב לבקר
    controller.send_command('1')

    # יצירת אירוע עצירה ו־threads
    stop_event = threading.Event()
    listener_thread = threading.Thread(target=listen_for_controller, args=(controller, stop_event), daemon=True)
    listener_thread.start()

    gui_thread = threading.Thread(target=sonar_gui, args=(stop_event,), daemon=True)
    gui_thread.start()

    # חלון קטן רק לכפתור יציאה (אפשר להרחיב)
    root = tk.Tk()
    root.title("Distance Debug View - Mode 1")

    exit_button = tk.Button(root, text="Exit Mode 1", command=root.destroy)
    exit_button.pack(padx=10, pady=10)

    # אפשרות להציג גם גרף debug ברים:
    # debug_bar_plot_thread_tk(root, stop_event)

    try:
        root.mainloop()   # המתנה עד סגירת מצב 1
    finally:
        # ניקוי threads בצורה מסודרת
        stop_event.set()
        listener_thread.join(timeout=2.0)
        gui_thread.join(timeout=2.0)
        try:
            plt.close('all')
        except Exception:
            pass
        print("Exited Mode 1, back to main menu.")

# -------- main --------
def main():
    port = "COM4"  # עדכן את הפורט לפי הצורך
    controller = MSPController(port)

    while True:
        choice = get_mode_from_user()

        if choice == '0':
            print("Exiting program.")
            break

        if choice == '1':
            controller.send_command('1')
            stop_event = threading.Event()
            # הפעלת טרד האזנה בלבד
            listener_thread = threading.Thread(target=listen_for_controller, args=(controller, stop_event))
            listener_thread.daemon = True
            listener_thread.start()

            print("Listening for data... type 'exit' to return to menu.")
            while True:
                user_input = input()
                if user_input.strip().lower() == 'exit':
                    break

            stop_event.set()
            listener_thread.join()
            print("Exited Mode 1.")

        if choice == '2':
            controller.send_command('2')
            degree = input("Enter degree between 0-180: ")
            deg = int(degree)
            deg = 600 + deg * 10
            deg = str(deg)
            controller.send_command(degree + '\n')

            stop_event = threading.Event()
            # הפעלת טרד האזנה בלבד
            listener_thread = threading.Thread(target=listen_for_controller, args=(controller, stop_event))
            listener_thread.daemon = True
            listener_thread.start()

            print("Listening for data... type 'exit' to return to menu.")
            while True:
                user_input = input()
                if user_input.strip().lower() == 'exit':
                    break

            stop_event.set()
            listener_thread.join()
            print("Exited Mode 2.")

        if choice == '3':
            controller.send_command('3')
            stop_event = threading.Event()
            # הפעלת טרד האזנה בלבד
            listener_thread = threading.Thread(target=listen_for_controller, args=(controller, stop_event))
            listener_thread.daemon = True
            listener_thread.start()

            print("Listening for data... type 'exit' to return to menu.")
            while True:
                user_input = input()
                if user_input.strip().lower() == 'exit':
                    break

            stop_event.set()
            listener_thread.join()
            print("Exited Mode 1.")


    controller.close()

if __name__ == "__main__":
    main()

# Serial Linker 
# Author: Sujai Rajan
# Date: October 2025
# Works with serial_linker_robot.py and config.json

import os
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import barcode_testing as decode



# --------------------------------------------------
# LOGIN VERIFICATION
# --------------------------------------------------
def verify_login(username, password):

    LOGIN_API_URL = "https://web.futaba.com/api/v1/users/login"
    payload = {"username": username, "password": password}
    try:
        r = requests.post(LOGIN_API_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("verified"):
            op_id = data.get("id")
            name = data.get("name", username)
            print(f"[INFO] Login verified for {name} (ID: {op_id})")
            return True, name, op_id
        else:
            reason = data.get("reason", "Invalid credentials")
            print("[WARN] Login failed:", reason)
            return False, None, None
    except Exception as e:
        print("[ERROR] Login request failed:", e)
        return False, None, None



# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
# CONFIG_PATH = "config.json"
CONFIG_PATH = os.path.expanduser("~/config.json")


# Function to load config
def load_config(path):
    # Safely load configuration, fall back to defaults.
    base = {
        "simulate_linking": False,
        "robot_main": {"home_pose": [0,0,0,0,0,0], "speed": 10, "port": "/dev/ttyAMA0", "baudrate": 115200},
        "camera": {"camera_index": 0, "camera_format": "MJPG", "debug_cam": True, "use_gst": False,
                   "resolution": [8000, 6000], "fps": 5, "save_path": "./captures"},
        "sensors_and_inputs": {"momentary_button_pin": 3, "toggle_switch_pin": 1,
                               "horse_shoe_sensor_pin": 2, "light_curtain_sensor_pin": 6},
        "outputs": {"led_strip_control_pin": 1, "tower_light_red_pin": 4,
                    "tower_light_green_pin": 3, "tower_light_buzzer_pin": 2},
        "boards": ["pcb_273", "pcb_274"],
        "default_board": "pcb_273",
        "robot_module": "serial_linker_robot"
    }
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                base.update(json.load(f))
            except Exception as e:
                print("[WARN] Bad config.json, using defaults:", e)
    else:
        print("[WARN] config.json not found, using defaults")
    return base

CFG = load_config(CONFIG_PATH)
SIMULATE = bool(CFG.get("simulate_linking", False))


# --------------------------------------------------
# SERIAL LINKING
# --------------------------------------------------
def link_serials(op_id, left_code, right_code):
    LINK_API_URL = "https://web.futaba.com/api/v1/sernums/link_and_depanel"
    payload = {
        "op_id": op_id,
        "sernum_sidea": left_code,
        "sernum_sideb": right_code
    }

    try:
        print(f"[INFO] Linking request → {payload}")
        r = requests.post(LINK_API_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=8)
        r.raise_for_status()
        resp = r.json()
        print("[INFO] Link API response:", resp)

        # Decide success
        if "success" in resp and resp["success"]:
            return True
        # Some APIs just return 200 OK with details
        if r.status_code == 200 and not "error" in resp:
            return True

    except Exception as e:
        print("[ERROR] Link request failed:", e)

    return False


# --------------------------------------------------
# IMPORT ROBOT CORE
# --------------------------------------------------
MyCobot320 = None
if not SIMULATE:
    try:
        from pymycobot.mycobot320 import MyCobot320
    except Exception as e:
        print("[WARN] pymycobot not found, enabling simulation mode ::", e)
        SIMULATE = True

robot_core = None
run_cycle = None
if not SIMULATE:
    try:
        import serial_linker_robot as robot_core
        run_cycle = getattr(robot_core, "run_cycle", None)
        print("[IsNFO] Robot core loaded successfully.")
    except Exception as e:
        print("[WARN] Could not import robot core ::", e)
        SIMULATE = True

# --------------------------------------------------
# BACKEND
# --------------------------------------------------
class Backend:
    """Hardware-safe wrapper for robot IO."""
    def __init__(self, cfg, simulate=False):
        self.cfg = cfg
        self.sim = simulate
        self.mc = None
        self._sim_board_present = False
        self._sim_start_pressed = False
        self._sim_toggle_on = True
        self._sim_light_curtain_clear = True
        self._connect()

    def _connect(self):
        if self.sim: 
            return
        try:

            import serial_linker_robot as robot_core
            self.mc =robot_core.init_robot(self.mc)
            if self.mc is None:
                print("Robot init failed")
            else: 
                print("robot init successful")
                print("[INFO] Connected to MyCobot320 via Robot Core")
        except Exception as e:
            print("[WARN] Robot connection failed, switching to simulation:", e)
            self.sim = True
            self.mc = None

    # --- Inputs ---
    def board_present(self):
        if self.sim: return self._sim_board_present
        pin = self.cfg["sensors_and_inputs"]["horse_shoe_sensor_pin"]
        return self.mc.get_basic_input(pin) == 0

    def board_removed(self): return not self.board_present()

    def start_pressed(self):
        if self.sim:
            v = self._sim_start_pressed
            self._sim_start_pressed = False
            return v
        pin = self.cfg["sensors_and_inputs"]["momentary_button_pin"]
        return self.mc.get_basic_input(pin) == 0

    def toggle_enabled(self):
        if self.sim: return self._sim_toggle_on
        pin = self.cfg["sensors_and_inputs"]["toggle_switch_pin"]
        return self.mc.get_basic_input(pin) == 0

    def curtain_clear(self):
        if self.sim: return self._sim_light_curtain_clear
        pin = self.cfg["sensors_and_inputs"]["light_curtain_sensor_pin"]
        return self.mc.get_basic_input(pin) == 0

    # --- Main robot cycle ---
    def do_robot_cycle(self, board):
        left, right = None, None
        try:
            if not self.sim and run_cycle:
                left, right = run_cycle()
            else:
                time.sleep(2)
                path = self.cfg["camera"]["save_path"]
                os.makedirs(path, exist_ok=True)
                left = os.path.join(path, f"{board}_left.jpg")
                right = os.path.join(path, f"{board}_right.jpg")
                open(left, "a").close()
                open(right, "a").close()
        except Exception as e:
            print("[ERROR] Robot cycle failed:", e)
        time.sleep(2)
        return (False, left, right)

    # --- Simulation toggles ---
    def sim_toggle_board(self): self._sim_board_present = not self._sim_board_present
    def sim_press_start(self): self._sim_start_pressed = True
    def sim_toggle_enable(self): self._sim_toggle_on = not self._sim_toggle_on
    def sim_toggle_curtain(self): self._sim_light_curtain_clear = not self._sim_light_curtain_clear

# --------------------------------------------------
# GUI APP
# --------------------------------------------------
class SerialLinkerApp(tk.Tk):
    C_BG = "#1b1b1b"
    C_LOADED = "#ffda33"
    C_LINKING = "#0078d7"
    C_PASS = "#28a745"
    C_FAIL = "#c50000"

    def __init__(self, backend, cfg):
        super().__init__()
        self.backend = backend
        self.cfg = cfg
        self.attributes("-fullscreen", True)
        
        self.title("Serial Linker HMI")
        self.configure(bg=self.C_BG)

        self.board = tk.StringVar(value=cfg.get("default_board", "pcb_273"))
        self.operator_name = ""
        self.state = "LOGIN"
        self.poll_job = None
        self.pulse_job = None
        self.cycle_latched = False
        self.operator_id = ""

        self._build_login()

    # ---------- Login ----------
    def _build_login(self):
        self._clear()
        outer = tk.Frame(self, bg=self.C_BG)
        outer.pack(expand=True, fill="both")

        frame = tk.Frame(outer, bg=self.C_BG)
        frame.place(relx=0.5, rely=0.5, anchor="center")


        tk.Label(frame, text="Serial Linker", fg="#00b7ff", bg=self.C_BG,
                 font=("Segoe UI", 48, "bold")).pack(pady=50)

        tk.Label(frame, text="Username", bg=self.C_BG, fg="white", font=("Segoe UI", 20)).pack()
        u_entry = tk.Entry(frame, font=("Segoe UI", 22), width=25)
        u_entry.pack(pady=10); u_entry.focus_set()

        tk.Label(frame, text="Password", bg=self.C_BG, fg="white", font=("Segoe UI", 20)).pack()
        p_entry = tk.Entry(frame, show="*", font=("Segoe UI", 22), width=25)
        p_entry.pack(pady=10)

        def login(event=None):
            u, p = u_entry.get().strip(), p_entry.get().strip()
            if not u:
                messagebox.showerror("Login Failed", "Please enter username or scan badge")
                return

            verified, name, op_id = verify_login(u, p)
            if verified:
                self.operator_name = name
                self.operator_id = op_id
                self._build_main()
            else:               
                messagebox.showerror("Login Failed", name)


        tk.Button(frame, text="LOGIN", bg="#00b7ff", fg="white", font=("Segoe UI", 20, "bold"),
                  relief="flat", width=16, height=2, command=login).pack(pady=50)
        u_entry.bind("<Return>", login)
        p_entry.bind("<Return>", login)

    # ---------- Main Screen ----------
    def _build_main(self):
        self._clear()
        self.state = "WAIT_REMOVE"

        header = tk.Frame(self, bg="#262626", height=90)
        header.pack(fill="x", side="top")
        tk.Label(header, text=f"Operator: {self.operator_name}", bg="#262626",
                 fg="#00ff9d", font=("Segoe UI", 24, "bold")).pack(side="left", padx=20, pady=20)

        mid = tk.Frame(header, bg="#262626")
        mid.pack(side="left", expand=True)
        tk.Label(mid, text="Board Type:", bg="#262626", fg="white",
                 font=("Segoe UI", 18)).pack(side="left", padx=(0,10))
        self.combo = ttk.Combobox(mid, textvariable=self.board,
                                  values=self.cfg.get("boards", ["pcb_273"]),
                                  font=("Segoe UI", 16), state="readonly", width=20)
        self.combo.pack(side="left")

        self.combo.bind("<<ComboboxSelected>>", self._on_board_changed)


        right = tk.Frame(header, bg="#262626")
        right.pack(side="right", padx=20)
        tk.Button(right, text="LOGOUT", bg="#ffb400", fg="black",
                  font=("Segoe UI", 14, "bold"), width=10, command=self._build_login).pack(side="left", padx=6)
        tk.Button(right, text="EXIT", bg="#e81123", fg="white",
                  font=("Segoe UI", 14, "bold"), width=10, command=self.destroy).pack(side="left", padx=6)

        self.canvas = tk.Canvas(self, bg=self.C_BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._set_status("REMOVE BOARD", self.C_LOADED, fg="black")
        # self.canvas.bind("<Configure>", lambda e: self._set_status("REMOVE BOARD", self.C_LOADED, fg="black"))

        if self.backend.sim:
            simbar = tk.Frame(self, bg=self.C_BG, height=60)
            simbar.pack(fill="x", side="bottom")
            tk.Label(simbar, text="SIMULATION MODE", bg=self.C_BG, fg="#00b7ff",
                     font=("Segoe UI", 14, "bold")).pack(side="left", padx=10)
            for txt, cmd in [("Board", self.backend.sim_toggle_board),
                             ("Start", self.backend.sim_press_start),
                             ("Enable", self.backend.sim_toggle_enable),
                             ("Curtain", self.backend.sim_toggle_curtain)]:
                tk.Button(simbar, text=txt, command=cmd).pack(side="left", padx=6)

        self._poll()

    # ---------- Polling & States ----------
    def _poll(self):
        try:
            board_present = self.backend.board_present()
            start = self.backend.start_pressed()
            enabled = self.backend.toggle_enabled()
            clear = self.backend.curtain_clear()

            if self.state == "WAIT_REMOVE":
                self._set_status("REMOVE BOARD", self.C_LOADED, fg="black")
                if not board_present:
                    self.state = "WAIT_BOARD"
                    self._set_status("WAITING FOR BOARD", self.C_BG)
                    self.canvas.bind("<Configure>", lambda e: self._set_status("WAITING FOR BOARD", self.C_BG))

            elif self.state == "WAIT_BOARD":
                if board_present:
                    self.state = "WAIT_START"
                    self._set_status("LOADED - PRESS START", self.C_LOADED, fg="black")

            elif self.state == "WAIT_START":
                if not board_present:
                    self.state = "WAIT_BOARD"
                    self._set_status("WAITING FOR BOARD", self.C_BG)
                elif start and enabled and clear:
                    self.state = "LINKING"
                    self._start_linking()

            elif self.state in ("PASS", "FAIL"):
                if not board_present:
                    self.state = "WAIT_BOARD"
                    self._set_status("WAITING FOR BOARD", self.C_BG)
        except Exception as e:
            print("[POLL ERROR]", e)
        finally:
            self.poll_job = self.after(120, self._poll)

    # ---------- Linking ----------
    def _start_linking(self):
        self._start_pulse()
        threading.Thread(target=self._link_thread, daemon=True).start()

    ## For Simulation Only
    # def _link_thread(self):
    #     ok, l, r = self.backend.do_robot_cycle(self.board.get())
    #     self.after(0, self._stop_pulse)
    #     if ok:
    #         self.after(0, lambda: self._set_status("LINKING SUCCESSFUL", self.C_PASS))
    #         self.state = "PASS"
    #     else:
    #         self.after(0, lambda: self._set_status("LINKING UNSUCCESSFUL", self.C_FAIL))
    #         self.state = "FAIL"


    def _link_thread(self):
        ok, left_path, right_path = self.backend.do_robot_cycle(self.board.get())
        self.after(0, self._stop_pulse)

        if left_path and right_path:
            try:
                reader = decode.get_barcode_reader()
                left_results = decode.decode_file(reader, left_path)
                right_results = decode.decode_file(reader, right_path)
                left_code = left_results[0].barcode_text if left_results else None
                right_code = right_results[0].barcode_text if right_results else None
                print(f"[INFO] Left SN: {left_code}, Right SN: {right_code}")
            except Exception as e:
                print("[ERROR] Barcode decode failed:", e)
                left_code = right_code = None
        else:
            left_code = right_code = None

        # --- Linking step ---
        link_success = False
        if left_code and right_code and self.operator_id:
            link_success = link_serials(self.operator_id, left_code, right_code)

        # --- GUI feedback ---
        if link_success:
            self.after(0, lambda: self._set_status("LINKING SUCCESSFUL", self.C_PASS))
            self.state = "PASS"
        else:
            self.after(0, lambda: self._set_status("LINKING FAILED", self.C_FAIL))
            self.state = "FAIL"





    # ---------- Pulse animation ----------
    def _start_pulse(self):
        self._pulse_tick(0, 1)

    def _stop_pulse(self):
        if self.pulse_job:
            try: self.after_cancel(self.pulse_job)
            except Exception: pass
            self.pulse_job = None
        self._set_status("LINKING...", self.C_LINKING)

    def _pulse_tick(self, step, direction):
        base = (0x00, 0x78, 0xd7)
        bright = (0x33, 0xa3, 0xff)
        t = step / 20.0
        r = int(base[0] + (bright[0]-base[0])*t)
        g = int(base[1] + (bright[1]-base[1])*t)
        b = int(base[2] + (bright[2]-base[2])*t)
        self._set_status("LINKING...", f"#{r:02x}{g:02x}{b:02x}")
        step += direction
        if step >= 20: direction = -1
        if step <= 0: direction = 1
        self.pulse_job = self.after(45, lambda: self._pulse_tick(step, direction))

    # ---------- Visuals ----------
    def _set_status(self, text, bg, fg=None):
        self.configure(bg=bg)
        self.canvas.configure(bg=bg)
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width() or 1440, self.canvas.winfo_height() or 900
        fg = fg or ("black" if bg == self.C_LOADED else "white")
        self.canvas.create_text(w//2, h//2, text=text, fill=fg, font=("Segoe UI", 68, "bold"))

    # ---------- Utilities ----------
    def _clear(self):
        for w in self.winfo_children():
            try: w.destroy()
            except Exception: pass

    def _on_board_changed(self, event=None):
        # Called when the operator changes board type.
        new_board = self.board.get()
        print(f"[INFO] Board switched to: {new_board}")
        try:
            import serial_linker_robot as robot_core
            if hasattr(robot_core, "set_board"):
                robot_core.set_board(new_board)
                print(f"[INFO] Robot core now using {new_board} configuration.")
            else:
                print("[WARN] Robot core missing set_board().")
        except Exception as e:
            print(f"[WARN] Could not update board config: {e}")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    backend = Backend(CFG, SIMULATE)
    app = SerialLinkerApp(backend, CFG)
    app.mainloop()

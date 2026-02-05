# Serial Linker 
# Author: Sujai Rajan
# Date: October 2025
# Works with serial_linker_robot.py and config.json

import os , json, time, threading, requests, subprocess, csv, shutil, sys
from urllib import response
from datetime import datetime
from tkinter import ttk, messagebox
import barcode_testing as decode
import tkinter as tk
from example import ProcessingServer, TaskState 

#### to be deleted after final prep
# --- Windows share / path helpers ---
SMB_MOUNT = "/mt/barcode_dropbox"   # adjust to your actual Linux mount point
UNC_ROOT  = r"\\hsv-dc2\barcode_reader"  # Windows UNC root seen by the server

def to_windows_path(path: str) -> str:

    return path.replace(SMB_MOUNT, UNC_ROOT).replace("/", "\\")

def ensure_on_share(local_path: str, subdir: str = "linker_line_1/image") -> str:
    """
    If local_path is not already under the SMB mount, copy it there with a unique timestamped name.
    Returns the Linux path on the SMB mount (not UNC).
    """
    # already under the mount?
    if local_path.startswith(SMB_MOUNT + "/"):
        return local_path

    os.makedirs(os.path.join(SMB_MOUNT, subdir), exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base = os.path.basename(local_path)
    root, ext = os.path.splitext(base)
    # keep extension; ensure .jpg
    ext = ext if ext else ".jpg"
    dest_linux = os.path.join(SMB_MOUNT, subdir, f"{root}_{ts}{ext}")

    # copy then sync to avoid zero-byte / partially-flushed files
    shutil.copy2(local_path, dest_linux)
    try:
        with open(dest_linux, "rb", buffering=0) as f:
            os.fsync(f.fileno())
    except Exception:
        pass
    return dest_linux

def poll_until_completed(server, task_id: str, poll_interval=2, timeout=90):
    """
    Polls the ProcessingServer until TaskState.Completed or timeout (seconds).
    Returns the final response dict (or None on timeout/error).
    """
    t0 = time.time()
    while True:
        try:
            res = server.get_async_task_status(task_id)
        except Exception as e:
            print("[ERROR] get_async_task_status failed:", e)
            return None

        state_val = res.get("State")
        try:
            state = TaskState(state_val)
        except Exception:
            state = None

        if state == TaskState.Completed:
            return res

        if time.time() - t0 > timeout:
            print(f"[ERROR] Task {task_id} timed out after {timeout}s")
            return None

        time.sleep(poll_interval)





# --------------------------------------------------
# LOGIN VERIFICATION
# --------------------------------------------------
def verify_login(username, password):

    LOGIN_API_URL = "https://web.futaba.com/api/v1/users/login_with_esd_check"
    LOGIN_API_URL = "https://web.futaba.com/api/v1/users/login" # Temporary no ESD check
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
# NETWORK SHARE MOUNTING
# --------------------------------------------------
def ensure_share_mounted(mount_point="/mt/barcode_dropbox"):
    """Ensure SMB share is mounted for cross-access image saving."""
    if not os.path.ismount(mount_point):
        cmd = [
            "sudo", "mount", "-t", "cifs", "//hsv-dc2/barcode_reader", mount_point,
            "-o", "credentials=/etc/samba/creds-hsv-dc2,iocharset=utf8,file_mode=0777,dir_mode=0777,noperm"
        ]
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(f"[WARN] Could not mount network share: {mount_point}")
            return False
        print(f"[INFO] Mounted network share at {mount_point}")
    return True

# --------------------------------------------------
# PATH CONVERSION
# --------------------------------------------------
def to_windows_path(path: str) -> str:
    """Convert a Linux-mounted SMB path to Windows UNC format."""
    # Example: /mnt/barcode_dropbox/checker_line_3/image/foo.jpg
    # → \\hsv-dc2\barcode_reader\checker_line_3\image\foo.jpg
    return path.replace("/mnt/barcode_dropbox", r"\\hsv-dc2\barcode_reader").replace("/", "\\")


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
POLL_INTERVAL_SEC = CFG.get("POLL_INTERVAL_SEC", 2)
MAX_POLL_ATTEMPTS = CFG.get("MAX_POLL_ATTEMPTS", 30)



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
        # Mount network share for barcode saving
        if ensure_share_mounted():
            print("[INFO] Network share mounted.")
        else:
            print("[WARN] Network share not mounted.")
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


    # def _link_thread(self):
    #     ok, left_path, right_path = self.backend.do_robot_cycle(self.board.get())
    #     self.after(0, self._stop_pulse)

    #     if left_path and right_path:
    #         try:
    #             reader = decode.get_barcode_reader()
    #             left_results = decode.decode_file(reader, left_path)
    #             right_results = decode.decode_file(reader, right_path)
    #             left_code = left_results[0].barcode_text if left_results else None
    #             right_code = right_results[0].barcode_text if right_results else None
    #             print(f"[INFO] Left SN: {left_code}, Right SN: {right_code}")
    #         except Exception as e:
    #             print("[ERROR] Barcode decode failed:", e)
    #             left_code = right_code = None
    #     else:
    #         left_code = right_code = None

    #     # --- Linking step ---
    #     link_success = False
    #     if left_code and right_code and self.operator_id:
    #         link_success = link_serials(self.operator_id, left_code, right_code)

    #     # --- GUI feedback ---
    #     if link_success:
    #         self.after(0, lambda: self._set_status("LINKING SUCCESSFUL", self.C_PASS))
    #         self.state = "PASS"
    #     else:
    #         self.after(0, lambda: self._set_status("LINKING FAILED", self.C_FAIL))
    #         self.state = "FAIL"


    def _link_thread(self):
        ok, left_path, right_path = self.backend.do_robot_cycle(self.board.get())
        self.after(0, self._stop_pulse)

        left_code = right_code = None

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

        # if left_path and right_path:
        #     try:
        #         server = ProcessingServer(host="10.40.17.62", port=9000)

        #         # --- Heartbeat ---
        #         hb = server.heartbeat()
        #         if not hb.get("GenericResult", False):
        #             print("[ERROR] Heartbeat failed! Server offline?")
        #             left_code = right_code = None
        #         else:
        #             # --- Submit LEFT ---
        #             left_path_win = to_windows_path(left_path)
        #             left_submit = server.submit(left_path_win)
        #             left_task_id = left_submit.get("TaskId")
        #             print(f"[INFO] Submitted LEFT image (task: {left_task_id})")

        #             # --- Poll for LEFT result ---
        #             left_code = None
        #             for attempt in range(MAX_POLL_ATTEMPTS):
        #                 res = server.get_async_task_status(left_task_id)
        #                 state_val = res.get("State")
        #                 if state_val == TaskState.Completed:
        #                     serials = res.get("Results", {}).get("serials", [])
        #                     if serials:
        #                         left_code = str(serials[0])
        #                     break
        #                 time.sleep(POLL_INTERVAL_SEC)

        #             # --- Submit RIGHT ---
        #             right_path_win = to_windows_path(right_path)
        #             right_submit = server.submit(right_path_win)
        #             right_task_id = right_submit.get("TaskId")
        #             print(f"[INFO] Submitted RIGHT image (task: {right_task_id})")

        #             # --- Poll for RIGHT result ---
        #             right_code = None
        #             for attempt in range(MAX_POLL_ATTEMPTS):
        #                 res = server.get_async_task_status(right_task_id)
        #                 state_val = res.get("State")
        #                 if state_val == TaskState.Completed:
        #                     result_serial = str(response["Results"]["serials"][0])
        #                     print(result_serial)
        #                     serials = res.get("Results", {}).get("serials", [])
        #                     if serials:
        #                         right_code = str(serials[0])
        #                     break
        #                 time.sleep(POLL_INTERVAL_SEC)

        #             print(f"[INFO] Left SN: {left_code}, Right SN: {right_code}")

        #     except Exception as e:
        #         print("[ERROR] Remote decode failed:", e)
        #         left_code = right_code = None
        # else:
        #     left_code = right_code = None

        # if left_path and right_path:
        #     try:
        #         # 1) Make sure both files live on the SMB share (so Windows server can read them)
        #         left_on_share  = ensure_on_share(left_path,  subdir="linker_line_1/image")
        #         right_on_share = ensure_on_share(right_path, subdir="linker_line_1/image")

        #         # 2) Convert to Windows UNC paths for the server
        #         left_unc  = to_windows_path(left_on_share)
        #         right_unc = to_windows_path(right_on_share)

        #         # 3) Connect + heartbeat
        #         server = ProcessingServer(host="10.40.17.62", port=9000)
        #         hb = server.heartbeat()
        #         if not hb.get("GenericResult", False):
        #             print("[ERROR] Heartbeat failed! Server offline?")
        #             left_code = right_code = None
        #         else:
        #             # 4) Submit LEFT, then poll until Completed
        #             left_submit = server.submit(left_unc)
        #             left_task_id = left_submit.get("TaskId")
        #             if not left_task_id:
        #                 print("[ERROR] Left submit missing TaskId:", left_submit)
        #             left_res = poll_until_completed(server, left_task_id, poll_interval=POLL_INTERVAL_SEC, timeout=MAX_POLL_ATTEMPTS*POLL_INTERVAL_SEC) if left_task_id else None
        #             left_code = None
        #             if left_res and left_res.get("Results"):
        #                 serials = left_res["Results"].get("serials", [])
        #                 if serials:
        #                     left_code = str(serials[0])
        #                 else:
        #                     print("[WARN] Left task completed but no serials in result:", left_res)

        #             # 5) Submit RIGHT, then poll until Completed
        #             right_submit = server.submit(right_unc)
        #             right_task_id = right_submit.get("TaskId")
        #             if not right_task_id:
        #                 print("[ERROR] Right submit missing TaskId:", right_submit)
        #             right_res = poll_until_completed(server, right_task_id, poll_interval=POLL_INTERVAL_SEC, timeout=MAX_POLL_ATTEMPTS*POLL_INTERVAL_SEC) if right_task_id else None
        #             right_code = None
        #             if right_res and right_res.get("Results"):
        #                 serials = right_res["Results"].get("serials", [])
        #                 if serials:
        #                     right_code = str(serials[0])
        #                 else:
        #                     print("[WARN] Right task completed but no serials in result:", right_res)

        #             print(f"[INFO] Left SN: {left_code}, Right SN: {right_code}")

        #     except Exception as e:
        #         print("[ERROR] Remote decode failed:", e)
        #         left_code = right_code = None
        # else:
        #     left_code = right_code = None




        # --- Linking step ---
        link_success = False
        if left_code and right_code and self.operator_id:
            link_success = link_serials(self.operator_id, left_code, right_code)

        # --- CSV Logging + Failed Image Backup ---
        try:
            base_dir = os.path.expanduser("~/log_serial_linker")
            log_dir = os.path.join(base_dir, "logs")
            failed_dir = os.path.join(base_dir, "failed_links")
            os.makedirs(log_dir, exist_ok=True)
            os.makedirs(failed_dir, exist_ok=True)

            # Daily log file
            today = datetime.now().strftime("%Y-%m-%d")
            csv_path = os.path.join(log_dir, f"link_log_{today}.csv")

            header = ["Timestamp", "Operator", "Board", "Left_SN", "Right_SN", "Result"]
            new_file = not os.path.exists(csv_path)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result_text = "PASS" if link_success else "FAIL"

            # Write entry
            with open(csv_path, "a", newline="") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(header)
                writer.writerow([
                    ts,
                    getattr(self, "operator_name", "Unknown"),
                    self.board.get(),
                    left_code or "N/A",
                    right_code or "N/A",
                    result_text
                ])

            # On failure — save copies of images with timestamp
            if not link_success and left_path and right_path:
                tag = datetime.now().strftime("%Y%m%d_%H%M%S")
                left_fail = os.path.join(failed_dir, f"FAIL_LEFT_{tag}.jpg")
                right_fail = os.path.join(failed_dir, f"FAIL_RIGHT_{tag}.jpg")
                shutil.copy(left_path, left_fail)
                shutil.copy(right_path, right_fail)
                print(f"[WARN] Saved failed pair images: {left_fail}, {right_fail}")

        except Exception as e:
            print("[ERROR] Logging or backup failed:", e)

        # --- GUI Feedback ---
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

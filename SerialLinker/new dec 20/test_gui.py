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
from dynamsoft_server_code import process_barcode



# __________________________________________________ Testing Functions __________________________________________________

# --- Windows share / path helpers ---
SMB_MOUNT = "/mt/barcode_dropbox"   # adjust to your actual Linux mount point
UNC_ROOT  = r"\\hsv-dc2\barcode_reader"  # Windows UNC root seen by the server



# --------------------------------------------------
# ROBOT BACKEND CLASS
# --------------------------------------------------
class Backend:
    """Hardware-safe wrapper for robot IO."""

    # Constructor Function                                                                             Backend_Function_1
    def __init__(self, cfg, simulate=False):
        self.cfg = cfg
        self.sim = simulate
        self.mc = None
        self._sim_board_present = False
        self._sim_start_pressed = False
        self._sim_toggle_on = True
        self._sim_light_curtain_clear = True
        self._connect()

    # ---------- Connect to Robot ----------                                                           Backend_Function_2
    def _connect(self):
        if self.sim: 
            return
        try:

            import serial_linker_robot as robot_core
            self.mc =robot_core.init_robot(self.mc)
            if self.mc is None:
                print("Robot init failed")
            else: 
                print("[ROBOT_INFO]robot initiation successful")
                # print("[INFO] Connected to MyCobot320 via Robot Core")
        except Exception as e:
            print("[WARN] Robot connection failed, switching to simulation:", e)
            self.sim = True
            self.mc = None


    # ---------- Input States ----------                                                                Backend_Function_3
    def board_present(self):
        if self.sim: return self._sim_board_present
        pin = self.cfg["sensors_and_inputs"]["horse_shoe_sensor_pin"]
        return self.mc.get_basic_input(pin) == 0


    # ---------- Input States ----------                                                                Backend_Function_4
    def board_removed(self): return not self.board_present()


    # ---------- Input States ----------                                                                Backend_Function_5
    def start_pressed(self):
        if self.sim:
            v = self._sim_start_pressed
            self._sim_start_pressed = False
            return v
        pin = self.cfg["sensors_and_inputs"]["momentary_button_pin"]
        return self.mc.get_basic_input(pin) == 0


    # ---------- Input States ----------                                                                Backend_Function_6
    def toggle_enabled(self):
        if self.sim: return self._sim_toggle_on
        pin = self.cfg["sensors_and_inputs"]["toggle_switch_pin"]
        return self.mc.get_basic_input(pin) == 0


    # ---------- Input States ----------                                                                Backend_Function_7
    def curtain_clear(self):
        if self.sim: return self._sim_light_curtain_clear
        pin = self.cfg["sensors_and_inputs"]["light_curtain_sensor_pin"]
        return self.mc.get_basic_input(pin) == 0


    #   ------- Robot Cycle ----------                                                                  Backend_Function_8
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
    
    #   ------- Robot Cycle (Single-Side) ----------                                                Backend_Function_9
    def do_robot_cycle_single_side(self, board):
        left = None
        try:
            if not self.sim and run_cycle_one_side:
                left = run_cycle_one_side()
            else:
                # --- Simulation fallback ---
                time.sleep(2)
                path = self.cfg["camera"]["save_path"]
                os.makedirs(path, exist_ok=True)
                left = os.path.join(path, f"{board}_left.jpg")
                open(left, "a").close()
        except Exception as e:
            print("[ERROR] Single-side robot cycle failed:", e)
        time.sleep(2)
        return left



    # --- Simulation toggles ---                                                                            
    def sim_toggle_board(self): self._sim_board_present = not self._sim_board_present                   # Backend_Function_10
    
    def sim_press_start(self): self._sim_start_pressed = True                                           # Backend_Function_11        
    
    def sim_toggle_enable(self): self._sim_toggle_on = not self._sim_toggle_on                          # Backend_Function_12
    
    def sim_toggle_curtain(self): self._sim_light_curtain_clear = not self._sim_light_curtain_clear     # Backend_Function_13



# --------------------------------------------------
# GUI APP CLASS
# --------------------------------------------------
class SerialLinkerApp(tk.Tk):

    # --- Color Constants ---
    C_BG = "#1b1b1b"
    C_LOADED = "#ffda33"
    C_LINKING = "#0078d7"
    C_PASS = "#28a745"
    C_FAIL = "#c50000"


    # Constructor Function                                                                     SerialLinkerApp_Function_1
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


    # ---------- Login ----------                                                               SerialLinkerApp_Function_2
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

            verified, name, op_id = self.verify_login(u, p)
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


    # ---------- Main Screen ----------                                                            SerialLinkerApp_Function_3
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


    # ---------- Polling & States ----------                                                               SerialLinkerApp_Function_4
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


    # ---------- Linking ----------                                                                         SerialLinkerApp_Function_5
    def _start_linking(self):
        self._start_pulse()
        threading.Thread(target=self._link_thread, daemon=True).start()


    # # ---------- Linking For Simulation Only ----------                                                     SerialLinkerApp_Function_6
    # if not SIMULATE:
    #     def _link_thread(self):
    #         ok, l, r = self.backend.do_robot_cycle(self.board.get())
    #         self.after(0, self._stop_pulse)
    #         if ok:
    #             self.after(0, lambda: self._set_status("LINKING SUCCESSFUL", self.C_PASS))
    #             self.state = "PASS"
    #         else:
    #             self.after(0, lambda: self._set_status("LINKING UNSUCCESSFUL", self.C_FAIL))
    #             self.state = "FAIL"



    def _link_thread(self):
        # --- Get current board config ---
        board_name = self.board.get()
        board_cfg = self.cfg.get(board_name, {})
        double_side_flag = board_cfg.get("double_side_flag", True)   # ✅ default True

        single_side, left_path, right_path = False, None, None

        if double_side_flag:
            single_side, left_path, right_path = self.backend.do_robot_cycle(self.board.get())
        else:
            left_path = self.backend.do_robot_cycle_single_side(self.board.get())
            single_side, right_path = True, None

        self.after(0, self._stop_pulse)

        left_code = right_code = None
        msg = "check board type"

        LOCAL_DECODE = True

        # Using Local Decoding - Dynamsoft Trial
        if LOCAL_DECODE:
            if left_path:
                try:
                    reader = decode.get_barcode_reader()
                    left_results = decode.decode_file(reader, left_path)
                    left_code = left_results[0].barcode_text if left_results else None
                    if double_side_flag:
                        right_results = decode.decode_file(reader, right_path)
                        right_code = right_results[0].barcode_text if right_results else None

                    print(f"[INFO] Left SN: {left_code}, Right SN: {right_code}")
                except Exception as e:
                    print("[ERROR] Barcode decode failed:", e)
                    left_code = right_code = None
            else:
                left_code = right_code = None


        # --- Decode both images using the Windows Dynamsoft server ---
        if not LOCAL_DECODE:
            if left_path and right_path:
                try:
                    # print("[INFO] Submitting images to remote barcode server...")

                    # Each call returns a decoded serial (or None)
                    left_code = process_barcode(["script", left_path, "/tmp/barcode_left.txt"])
                    right_code = process_barcode(["script", right_path, "/tmp/barcode_right.txt"])

                    if left_code and right_code:
                        msg = f"Decoded successfully: {left_code}, {right_code}"
                    elif left_code or right_code:
                        msg = f"Only one side decoded (Left={bool(left_code)}, Right={bool(right_code)})"
                    else:
                        msg = "No barcode detected on either side"

                    print(f"[BARCODE_PROCESSED] Left SN: {left_code}, Right SN: {right_code}")

                except Exception as e:
                    msg = f"Remote decode failed: {e}"
                    print("[ERROR]", msg)
                    left_code = right_code = None
            else:
                msg = "No image captured"
                left_code = right_code = None


        # --- Linking step ---
        link_success = False
        link_msg = msg
        if left_code and self.operator_id:
            try:
                if double_side_flag and right_code:
                    link_success, link_msg = self.link_serials(self.operator_id, left_code, right_code)
                else:
                    link_success, link_msg = self.depanel_only(self.operator_id, left_code)
            except Exception as e:
                link_msg = f"Linking exception: {e}"
                print("[ERROR]", link_msg)

        # --- CSV Logging + Failed Image Backup ---
        try:
            self.log_to_csv(operator=self.operator_name,
                            board=self.board.get(),
                            left_sn=left_code,
                            right_sn=right_code,
                            result=link_success,
                            msg=link_msg,
                            left_img=left_path,
                            right_img=right_path)
        except Exception as e:
            print("[ERROR] Logging failed:", e)

        # --- GUI Feedback ---
        if link_success:
            self.after(0, lambda: self._set_status("LINKING SUCCESSFUL", self.C_PASS, subtext=link_msg))
            self.state = "PASS"
        else:
            self.after(0, lambda: self._set_status("LINKING FAILED", self.C_FAIL, subtext=link_msg))
            self.state = "FAIL"



    # ---------- Pulse animation ----------                                                               SerialLinkerApp_Function_8
    def _start_pulse(self):
        self._pulse_tick(0, 1)


    # ---------- Stop Pulse ----------                                                                     SerialLinkerApp_Function_9   
    def _stop_pulse(self):
        if self.pulse_job:
            try: self.after_cancel(self.pulse_job)
            except Exception: pass
            self.pulse_job = None
        self._set_status("LINKING...", self.C_LINKING)


    # ---------- Pulse Tick ----------                                                                      SerialLinkerApp_Function_10
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


    # ---------- Status Display ---------- SerialLinkerApp_Function_9   
    def _set_status(self, text, bg, fg=None, subtext=None):
        self.configure(bg=bg)
        self.canvas.configure(bg=bg)
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width() or 1440, self.canvas.winfo_height() or 900
        fg = fg or ("black" if bg == self.C_LOADED else "white")
        # --- Main large text ---
        self.canvas.create_text(
            w // 2, h // 2 - 30,
            text=text,
            fill=fg,
            font=("Segoe UI", 68, "bold"),
            justify="center"
        )
        # --- Optional smaller subtext below --- 
        if subtext:
            self.canvas.create_text(
                w // 2, h // 2 + 60,
                text=subtext,
                fill="#d0d0d0",
                font=("Segoe UI", 26, "bold"),
                justify="center",
                width=w - 200  # wrap slightly within the window
            )


    # ---------- Board Change Handler ----------                                                           SerialLinkerApp_Function_11
    def _on_board_changed(self, event=None):
        # Called when the operator changes board type.
        new_board = self.board.get()
        print(f"[ROBOT_CONFIG_UPDATE] Board switched to: {new_board}")
        try:
            import serial_linker_robot as robot_core
            if hasattr(robot_core, "set_board"):
                robot_core.set_board(new_board)
                print(f"[ROBOT_CONFIG_UPDATE] Robot core now using {new_board} configuration.")
            else:
                print("[ROBOT_CONFIG_UPDATE] Robot core missing set_board().")
        except Exception as e:
            print(f"[ROBOT_CONFIG_UPDATE] Could not update board config: {e}")


    # ---------- Utilities ----------                                                                       SerialLinkerApp_Function_12
    def _clear(self):
        for w in self.winfo_children():
            try: w.destroy()
            except Exception: pass


    # ---------- Verify Login ----------                                                                    SerialLinkerApp_Function_13
    def verify_login(self,username, password):

        LOGIN_API_URL = "https://web.futaba.com/api/v1/users/login_with_esd_check"
        if username == "srajan":
            LOGIN_API_URL = "https://web.futaba.com/api/v1/users/login" # Temporary no ESD check
        payload = {"username": username, "password": password}
        try:
            r = requests.post(LOGIN_API_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=5)
            r.raise_for_status()
            data = r.json()
            if data.get("verified"):
                op_id = data.get("id")
                name = data.get("name", username)
                print(f"[API_INFO] Login verified for {name} (ID: {op_id})")
                return True, name, op_id
            else:
                reason = data.get("reason", "Invalid credentials")
                print("[API_INFO] Login failed:", reason)
                return False, None, None
        except Exception as e:
            print("[API_INFO] Login request failed:", e)
            return False, None, None
        

    # ---------- Link Serial Numbers ----------                                                               SerialLinkerApp_Function_14
    def link_serials(self, op_id, left_code, right_code):

        LINK_API_URL = "https://web.futaba.com/api/v1/sernums/link_and_depanel"
        payload = {
            "op_id": op_id,
            "sernum_sidea": left_code,
            "sernum_sideb": right_code
        }

        try:
            # print(f"[API_INFO] Linking request → {payload}")
            r = requests.post(LINK_API_URL, json=payload,headers={"Content-Type": "application/json"}, timeout=10)

            # --- Handle HTTP errors cleanly ---
            if r.status_code >= 400:
                try:
                    err = r.json().get("error", r.text)
                except Exception:
                    err = r.text
                print(f"[API_INFO] HTTP {r.status_code}: {err}")
                return False, f"HTTP {r.status_code}: {err}"

            # --- Parse response JSON ---
            try:
                resp = r.json()
            except Exception:
                print("[API_INFO] Response not JSON:", r.text)
                return False, "Invalid response from server"

            print("[API_INFO] Link API response:", resp)

            # --- Interpret common response formats ---
            # Case 1: newer API with "linked" and "info"
            if "linked" in resp:
                linked = bool(resp["linked"])
                msg = resp.get("info", "No info returned")
                return linked, msg

            # Case 2: legacy API with "success"
            if "success" in resp:
                ok = bool(resp["success"])
                msg = resp.get("info") or resp.get("message") or ("Success" if ok else "Failed")
                return ok, msg

            # Case 3: explicit error message
            if "error" in resp:
                return False, str(resp["error"])

            # Fallback: any other 200 OK response
            return True, resp.get("info", "Linked successfully-default")

        except requests.exceptions.Timeout:
            print("[API_INFO] Link request timed out.")
            return False, "Request timed out"

        except Exception as e:
            print("[API_INFO] Link request failed:", e)
            return False, str(e)

    # ---------- Log to CSV ----------                                                                     SerialLinkerApp_Function_15
    def log_to_csv(self, operator, board, left_sn, right_sn, result, msg, left_img=None, right_img=None):
        """Append result to CSV and back up only images that failed to decode."""

        base_dir = os.path.expanduser("/mt/barcode_dropbox/logs")
        log_dir = os.path.join(base_dir, "logs")
        failed_dir = os.path.join(base_dir, "failed_links")
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(failed_dir, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        csv_path = os.path.join(log_dir, f"link_log_{today}.csv")

        header = ["Timestamp", "Operator", "Board", "Left_SN", "Right_SN", "Result", "Message"]
        new_file = not os.path.exists(csv_path)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_text = "PASS" if result else "FAIL"

        # --- Write result to CSV ---
        try:
            with open(csv_path, "a", newline="") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(header)
                writer.writerow([
                    ts,
                    operator or "Unknown",
                    board or "Unknown",
                    left_sn or "N/A",
                    right_sn or "N/A",
                    result_text,
                    msg or ""
                ])
            print(f"[DEBUG_INFO] Logged result to CSV → {csv_path}")
        except Exception as e:
            print(f"[DEBUG_INFO] Could not write to CSV: {e}")
            return

        # --- Save only failed decode images ---
        try:
            tag = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Left image has no serial number → save it
            if (not left_sn or left_sn in ["", "N/A", None]) and left_img and os.path.exists(left_img):
                left_fail = os.path.join(failed_dir, f"FAIL_LEFT_NO_SN_{tag}.jpg")
                shutil.copy(left_img, left_fail)
                print(f"[DEBUG_INFO] Saved left failed image: {left_fail}")

            # Right image has no serial number → save it
            if (not right_sn or right_sn in ["", "N/A", None]) and right_img and os.path.exists(right_img):
                right_fail = os.path.join(failed_dir, f"FAIL_RIGHT_NO_SN_{tag}.jpg")
                shutil.copy(right_img, right_fail)
                print(f"[DEBUG_INFO] Saved right failed image: {right_fail}")

        except Exception as e:
            print(f"[DEBUG_INFO] Could not copy failed images: {e}")



    # ---------- Ensure It is mounted ----------                                                               SerialLinkerApp_Function_16
    def ensure_on_share(local_path: str, subdir: str = "linker_line_1/image") -> str:
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
    
    # ---------- Depanel Only API Call ----------                                                               SerialLinkerApp_Function_17
    def depanel_only(self, op_id, serial_code):
        DEPANEL_API_URL = "https://web.futaba.com/api/v1/sernums/depanel"
        payload = {
            "op_id": op_id,
            "sernum": serial_code
        }

        try:
            # print(f"[API_INFO] Depanel request → {payload}")
            r = requests.post(DEPANEL_API_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=10)

            # --- Handle HTTP errors cleanly ---
            if r.status_code >= 400:
                try:
                    err = r.json().get("error", r.text)
                except Exception:
                    err = r.text
                print(f"[API_INFO] HTTP {r.status_code}: {err}")
                return False, f"HTTP {r.status_code}: {err}"

            # --- Parse response JSON ---
            try:
                resp = r.json()
            except Exception:
                print("[API_INFO] Response not JSON:", r.text)
                return False, "Invalid response from server"

            print("[API_INFO] Depanel API response:", resp)

            # --- Interpret common response formats ---
            # Case 1: newer API with "depanelled" and "info"
            if "depanelled" in resp:
                ok = bool(resp["depanelled"])
                msg = resp.get("info", "No info returned")
                return ok, msg

            # Case 2: legacy API with "success"
            if "success" in resp:
                ok = bool(resp["success"])
                msg = resp.get("info") or resp.get("message") or ("Depanel successful" if ok else "Depanel failed")
                return ok, msg

            # Case 3: explicit error message
            if "error" in resp:
                return False, str(resp["error"])

            # Fallback: any other 200 OK response
            return True, resp.get("info", "Depanel successful-default")

        except requests.exceptions.Timeout:
            print("[API_INFO] Depanel request timed out.")
            return False, "Request timed out"

        except Exception as e:
            print("[API_INFO] Depanel request failed:", e)
            return False, str(e)


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
            print(f"[NETWORK_INFO] Could not mount network share: {mount_point}")
            return False
        # print(f"[NETWORK_INFO] Mounted network share at {mount_point}")
    return True


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
# CONFIG_PATH = "config.json"
CONFIG_PATH = os.path.expanduser("~/config.json")

# Function to load config                                                                                           Function_1
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
                print("[CONFIG_UPDATE] Bad config.json, using defaults:", e)
    else:
        print("[CONFIG_UPDATE] config.json not found, using defaults")
    return base

CFG = load_config(CONFIG_PATH)
SIMULATE = bool(CFG.get("simulate_linking", False))
POLL_INTERVAL_SEC = CFG.get("POLL_INTERVAL_SEC", 2)
MAX_POLL_ATTEMPTS = CFG.get("MAX_POLL_ATTEMPTS", 30)


# --------------------------------------------------
# IMPORT ROBOT CORE
# --------------------------------------------------
MyCobot320 = None
if not SIMULATE:
    try:
        from pymycobot.mycobot320 import MyCobot320
    except Exception as e:
        print("[ROBOT_INFO] pymycobot not found, enabling simulation mode ::", e)
        # SIMULATE = True
        print("[ROBOT_INFO] Simulation mode disabled by CJ")
        SIMULATE = False

robot_core = None
run_cycle = None
run_cycle_one_side = None
if not SIMULATE:
    try:
        import serial_linker_robot as robot_core
        run_cycle = getattr(robot_core, "run_cycle", None)
        run_cycle_one_side = getattr(robot_core, "run_cycle_one_side", None)
        print("[ROBOT_INFO] Robot core loaded successfully.")
        print("[ROBOT_INFO] PROGRAMMED by CJ ")
        # Mount network share for barcode saving
        if ensure_share_mounted():
            print("[NETWORK_INFO] Network share mounted.")
        else:
            print("[ROBOT_INFO] Network share not mounted.")
    except Exception as e:
        print("[ROBOT_INFO] Could not import robot core ::", e)
        SIMULATE = True


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    backend = Backend(CFG, SIMULATE)
    app = SerialLinkerApp(backend, CFG)
    app.mainloop()

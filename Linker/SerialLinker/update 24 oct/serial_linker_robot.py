# Author: Sujai Rajan
# Date : September 2025
# Code Cleanup : OCT 2025


import json
import os
import cv2
import time
from pymycobot.mycobot320 import MyCobot320



CONFIG_PATH = os.path.expanduser("~/config.json")


# ---------- Load Config ----------
with open(CONFIG_PATH) as f:
    config = json.load(f)

robot_cfg = config["robot_main"]
cam_cfg = config["camera"]
inputs_cfg = config["sensors_and_inputs"]
outputs_cfg = config["outputs"]



# ---------- Helper Function ------
current_board_name = "pcb_273"
current_board_cfg = config.get(current_board_name,{})

LOGGING_TOGGLE = config.get("logging", False)

if LOGGING_TOGGLE:

    import logging
    # ---------- Setup Logging ----------
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # Remove all handlers associated with the root logger object.
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Add console handler
    logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    # fh = logging.FileHandler('/home/er/Documents/robot_log.log')
    fh = logging.StreamHandler()
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)




def set_board(board_name):
    # Switch the current PCB configuration dynamically.
    global current_board_name, current_board_cfg
    if board_name in config:
        current_board_name = board_name
        current_board_cfg = config[board_name]
        if LOGGING_TOGGLE: logger.warning(f"Board configuration switched to: {board_name}")
    else:
        if LOGGING_TOGGLE: logger.error(f"Unknown board name in config: {board_name}")



# ---------- Robot Init ----------
mc = None

def init_robot(existing=None):
    """Attach an existing MyCobot320 instance or create a new one once."""
    global mc
    try: 
        if existing:
            mc = existing
            return mc
        if mc is not None: 
            print("Reusing")
            return mc
        if mc is None:
            # print("Connecting to robot") 
            mc = MyCobot320(robot_cfg["port"], robot_cfg["baudrate"])
            mc.power_on()
            mc.focus_all_servos()
            time.sleep(1)
            # print("Connected to the robot")
        return mc
    
    except Exception as e:
        print("[ERROR] Could not connect to MyCobot:",e)
        mc = None
        return None

# ---------- Camera Init ----------
def capture_image(side):
    """Capture a stable, non-black image; retry automatically if dark or too small."""
    
    # --- Choose backend ---
    if cam_cfg["use_gst"]:
        print("Using GStreamer pipeline for camera")
        gst = (f"v4l2src device=/dev/video0 ! "
               f"image/jpeg, width={cam_cfg['resolution'][0]}, height={cam_cfg['resolution'][1]}, framerate={cam_cfg['fps']}/1 ! "
               "jpegdec ! videoconvert ! appsink")
        cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)
        
    else:
        cap = cv2.VideoCapture(cam_cfg["camera_index"], cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_cfg["resolution"][0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_cfg["resolution"][1])
        cap.set(cv2.CAP_PROP_FPS, cam_cfg["fps"])
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*cam_cfg["camera_format"]))
        cap.set(cv2.CAP_PROP_BRIGHTNESS, cam_cfg["controls"]["brightness"]["value"])
        cap.set(cv2.CAP_PROP_CONTRAST, cam_cfg["controls"]["contrast"]["value"])
        cap.set(cv2.CAP_PROP_SATURATION, cam_cfg["controls"]["saturation"]["value"])
        cap.set(cv2.CAP_PROP_HUE, cam_cfg["controls"]["hue"]["value"])
        cap.set(cv2.CAP_PROP_GAMMA, cam_cfg["controls"]["gamma"]["value"])
        cap.set(cv2.CAP_PROP_SHARPNESS, cam_cfg["controls"]["sharpness"]["value"])
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # --- Debug info ---
    if cam_cfg["debug_cam"] and LOGGING_TOGGLE:
        logger.warning(f"Camera Properties: "
                       f"{cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)} "
                       f"at {cap.get(cv2.CAP_PROP_FPS)} FPS")

    # --- Stabilize and flush buffer ---
    time.sleep(0.5)
    for _ in range(3):
        cap.read()
        time.sleep(0.05)

    file_path = os.path.join(cam_cfg["save_path"], f"{side}_image.jpg")

    # --- Capture attempts with validation ---
    for attempt in range(3):
        ret, frame = cap.read()
        if not ret or frame is None:
            if LOGGING_TOGGLE:
                logger.warning(f"{side}: Capture failed on attempt {attempt+1}, retrying...")
            time.sleep(0.3)
            continue

        # Check brightness to avoid black frame
        if frame.mean() < 5:
            if LOGGING_TOGGLE:
                logger.warning(f"{side}: Dark frame detected (mean={frame.mean():.2f}), retrying...")
            time.sleep(0.3)
            continue

        # Save image and verify size
        cv2.imwrite(file_path, frame)
        size_kb = os.path.getsize(file_path) / 1024
        if size_kb < 500:
            if LOGGING_TOGGLE:
                logger.warning(f"{side}: Small file ({size_kb:.1f} KB), retrying...")
            time.sleep(0.3)
            continue

        # Valid capture
        if LOGGING_TOGGLE:
            logger.warning(f"{side}: Capture OK ({size_kb:.1f} KB, mean={frame.mean():.1f})")
        cap.release()
        return file_path

    # --- If all attempts failed ---
    if LOGGING_TOGGLE:
        logger.error(f"{side}: Capture failed after 3 attempts (black/small image).")
    cap.release()
    return None


# ---------- IO Control ----------

def light_on():
    if LOGGING_TOGGLE: logger.warning("Turning light ON")
    mc.set_basic_output(outputs_cfg["led_strip_control_pin"], 0)

def light_off():
    if LOGGING_TOGGLE: logger.warning("Turning light OFF")
    mc.set_basic_output(outputs_cfg["led_strip_control_pin"], 1)

def tower_light_red_on():
    if LOGGING_TOGGLE: logger.warning("Turning Tower Light RED ON")
    mc.set_basic_output(outputs_cfg["tower_light_red_pin"], 0)

def tower_light_red_off():
    if LOGGING_TOGGLE: logger.warning("Turning Tower Light RED OFF")
    mc.set_basic_output(outputs_cfg["tower_light_red_pin"], 1)

# def tower_light_yellow_on():
#     if LOGGING_TOGGLE: logger.warning("Turning Tower Light YELLOW ON")
#     mc.set_basic_output(outputs_cfg["tower_light_yellow_pin"], 0)

# def tower_light_yellow_off():
#     if LOGGING_TOGGLE: logger.warning("Turning Tower Light YELLOW OFF")
#     mc.set_basic_output(outputs_cfg["tower_light_yellow_pin"], 1)

def tower_light_green_on():
    if LOGGING_TOGGLE: logger.warning("Turning Tower Light GREEN ON")  
    mc.set_basic_output(outputs_cfg["tower_light_green_pin"], 0)

def tower_light_green_off():
    if LOGGING_TOGGLE: logger.warning("Turning Tower Light GREEN OFF")
    mc.set_basic_output(outputs_cfg["tower_light_green_pin"], 1)

def buzzer_on():
    if LOGGING_TOGGLE: logger.warning("Turning Buzzer ON")
    mc.set_basic_output(outputs_cfg["tower_light_buzzer_pin"], 0)

def buzzer_off():
    if LOGGING_TOGGLE: logger.warning("Turning Buzzer OFF")
    mc.set_basic_output(outputs_cfg["tower_light_buzzer_pin"], 1)

def cycle_through_outputs():
    tower_light_red_on()
    time.sleep(1)
    tower_light_red_off()
    # tower_light_yellow_on()
    # time.sleep(1)
    # tower_light_yellow_off()
    light_on()
    time.sleep(1)
    light_off()
    tower_light_green_on()
    time.sleep(1)
    tower_light_green_off()
    buzzer_on()
    time.sleep(1)
    buzzer_off()
    

def board_presence():
    return mc.get_basic_input(inputs_cfg["horse_shoe_sensor_pin"]) == 0

def board_removed():
    return mc.get_basic_input(inputs_cfg["horse_shoe_sensor_pin"]) == 1

# ---------- Wait for Trigger ----------
def wait_for_trigger():
    last_log = 0 # To limit log frequency
    if LOGGING_TOGGLE: logger.warning("Press Green Button to Initiate Scan Cycle")
    while True:
        if mc.get_basic_input(inputs_cfg["toggle_switch_pin"]) == 0:
            mc.power_on()
            if mc.get_basic_input(inputs_cfg["light_curtain_sensor_pin"]) == 0:
                if mc.get_basic_input(inputs_cfg["horse_shoe_sensor_pin"]) == 0:
                    if mc.get_basic_input(inputs_cfg["momentary_button_pin"]) == 0:
                        if LOGGING_TOGGLE: logger.warning("Start signal received.")
                        return
                    else :
                        if time.time() - last_log > 3:  # Log every 3 seconds
                            last_log = time.time()
                            if LOGGING_TOGGLE: logger.warning("Waiting for start button...")
                else:
                    if LOGGING_TOGGLE: logger.warning("No board detected.")
            else:
                if LOGGING_TOGGLE: logger.warning("Light curtain interrupted.")
        else:
            if LOGGING_TOGGLE: logger.warning("System not enabled. Toggle switch is OFF.")
            mc.power_off()


        


# ---------- Robot Movement ----------
def go_home():
    if LOGGING_TOGGLE: logger.warning("Moving to home position")
    mc.send_angles(robot_cfg["home_pose"], robot_cfg["speed"])

def go_left():
    if LOGGING_TOGGLE: logger.warning("Moving to left position")
    pose = current_board_cfg.get("left_pose")
    if pose: mc.send_angles(pose, robot_cfg["speed"])

def go_right():
    if LOGGING_TOGGLE: logger.warning("Moving to right position")
    mc.send_angles(current_board_cfg["right_pose"], robot_cfg["speed"])

def go_before_home():
    if LOGGING_TOGGLE: logger.warning("Moving to before home position")
    mc.send_angles(robot_cfg["before_home"], robot_cfg["speed"])



# ---------- Main Process ----------
def run_cycle_old():
    # Wait for trigger and turn on light
    wait_for_trigger()
    tower_light_green_off()
    light_on()

    # Home position to start
    go_home()
    time.sleep(0.1)
        
    # Move to left and capture image    
    go_left()
    time.sleep(0.05)
    left_image_path = capture_image("left")

    go_before_home()    
    # time.sleep(0.1)
    
    # Move to right and capture image
    go_right()
    time.sleep(0.05)
    right_image_path = capture_image("right")

    go_before_home()
    # time.sleep(0.1)

    # Turn off light and return home
    go_home()
    time.sleep(2)
    light_off()
    
    if LOGGING_TOGGLE: logger.warning("Cycle complete. Images saved: %s, %s", left_image_path, right_image_path)

    return left_image_path or None , right_image_path or None


def run_cycle():

    if mc is None:
        raise RuntimeError("Robot not initialized. Call init_robot() before run_cycle().")

    if mc.get_basic_input(inputs_cfg["toggle_switch_pin"]) == 0:
            mc.power_on()
            if mc.get_basic_input(inputs_cfg["light_curtain_sensor_pin"]) == 0:
                if mc.get_basic_input(inputs_cfg["horse_shoe_sensor_pin"]) == 0:
                    
                    tower_light_red_off()
                    tower_light_green_off()
                    light_on()

                    # Home position to start
                    go_home()
                    time.sleep(0.1)
                        
                    # Move to left and capture image    
                    go_left()
                    time.sleep(2)

                    left_image_path = capture_image("left")

                    go_before_home()    
                    # time.sleep(0.1)
                    
                    # Move to right and capture image
                    go_right()
                    time.sleep(2)

                    right_image_path = capture_image("right")

                    go_before_home()
                    # time.sleep(0.1)

                    # Turn off light and return home
                    go_home()

                    light_off()
                    
                    if LOGGING_TOGGLE: logger.warning("Cycle complete. Images saved: %s, %s", left_image_path, right_image_path)


                    return left_image_path, right_image_path

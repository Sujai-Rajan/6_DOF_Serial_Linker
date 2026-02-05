# Author: Sujai Rajan
# Date : September 2025



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


import json
import os
import cv2
import time

from pymycobot.mycobot320 import MyCobot320

# ---------- Load Config ----------
with open("/home/er/Documents/config.json") as f:
    config = json.load(f)

robot_cfg = config["robot_main"]
cam_cfg = config["camera"]
inputs_cfg = config["sensors_and_inputs"]
outputs_cfg = config["outputs"]

pcb_273_cfg = config["pcb_273"]


# ---------- Robot Init ----------
mc = MyCobot320(robot_cfg["port"], robot_cfg["baudrate"])
mc.power_on()
mc.focus_all_servos()
time.sleep(1)


# ---------- Camera Init ----------
def capture_image(side):
    if cam_cfg["use_gst"]:
        print("Using GStreamer pipeline for camera")
        gst = (f"v4l2src device=/dev/video0 ! "
            f"image/jpeg, width={cam_cfg['resolution'][0]}, height={cam_cfg['resolution'][1]}, framerate={cam_cfg['fps']}/1 ! "
            "jpegdec ! videoconvert ! appsink"
        )
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
        
    
    if cam_cfg["debug_cam"]:
        logger.warning(f"Camera Properties: {cap.get(cv2.CAP_PROP_FRAME_WIDTH)}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT)} at {cap.get(cv2.CAP_PROP_FPS)} FPS")

    time.sleep(2)
    ret, frame = cap.read()
    time.sleep(2)


    if ret:
        logger.warning("Camera capture successful for %s side", side)
        file_path = os.path.join(cam_cfg["save_path"], f"{side}_image.jpg")
        cv2.imwrite(file_path, frame)
        logger.warning("Saved %s image to %s", side, file_path)

    if not ret:
            logger.error("Camera capture failed for %s side", side)
            return None
    

    # cap.release()
    return file_path


# ---------- IO Control ----------

def light_on():
    logger.warning("Turning light ON")
    mc.set_basic_output(outputs_cfg["led_strip_control_pin"], 0)

def light_off():
    logger.warning("Turning light OFF")
    mc.set_basic_output(outputs_cfg["led_strip_control_pin"], 1)

def tower_light_red_on():
    logger.warning("Turning Tower Light RED ON")
    mc.set_basic_output(outputs_cfg["tower_light_red_pin"], 0)

def tower_light_red_off():
    logger.warning("Turning Tower Light RED OFF")
    mc.set_basic_output(outputs_cfg["tower_light_red_pin"], 1)

# def tower_light_yellow_on():
#     logger.warning("Turning Tower Light YELLOW ON")
#     mc.set_basic_output(outputs_cfg["tower_light_yellow_pin"], 0)

# def tower_light_yellow_off():
#     logger.warning("Turning Tower Light YELLOW OFF")
#     mc.set_basic_output(outputs_cfg["tower_light_yellow_pin"], 1)

def tower_light_green_on():
    logger.warning("Turning Tower Light GREEN ON")  
    mc.set_basic_output(outputs_cfg["tower_light_green_pin"], 0)

def tower_light_green_off():
    logger.warning("Turning Tower Light GREEN OFF")
    mc.set_basic_output(outputs_cfg["tower_light_green_pin"], 1)

def buzzer_on():
    logger.warning("Turning Buzzer ON")
    mc.set_basic_output(outputs_cfg["tower_light_buzzer_pin"], 0)

def buzzer_off():
    logger.warning("Turning Buzzer OFF")
    mc.set_basic_output(outputs_cfg["tower_light_buzzer_pin"], 1)

def cycle_through_lights():
    tower_light_red_on()
    time.sleep(1)
    tower_light_red_off()
    tower_light_green_on()
    time.sleep(1)
    tower_light_green_off()
    # tower_light_yellow_on()
    # time.sleep(1)
    # tower_light_yellow_off()
    light_on()
    time.sleep(1)
    light_off()
    buzzer_on()
    time.sleep(0.2)
    buzzer_off()
    

def board_presence():
    return mc.get_basic_input(inputs_cfg["horse_shoe_sensor_pin"]) == 0

def board_removed():
    return mc.get_basic_input(inputs_cfg["horse_shoe_sensor_pin"]) == 1

# ---------- Wait for Trigger ----------
def wait_for_trigger():
    last_log = 0 # To limit log frequency
    logger.warning("Press Green Button to Initiate Scan Cycle")
    while True:
        if mc.get_basic_input(inputs_cfg["toggle_switch_pin"]) == 0:
            mc.power_on()
            if mc.get_basic_input(inputs_cfg["light_curtain_sensor_pin"]) == 0:
                if mc.get_basic_input(inputs_cfg["horse_shoe_sensor_pin"]) == 0:
                    if mc.get_basic_input(inputs_cfg["momentary_button_pin"]) == 0:
                        logger.warning("Start signal received.")
                        return
                    else :
                        if time.time() - last_log > 3:  # Log every 3 seconds
                            last_log = time.time()
                            logger.warning("Waiting for start button...")
                else:
                    logger.warning("No board detected.")
            else:
                logger.warning("Light curtain interrupted.")
        else:
            logger.warning("System not enabled. Toggle switch is OFF.")
            mc.power_off()
        


# ---------- Robot Movement ----------
def go_home():
    logger.warning("Moving to home position")
    mc.send_angles(robot_cfg["home_pose"], robot_cfg["speed"])

def go_left():
    logger.warning("Moving to left position")
    mc.send_angles(pcb_273_cfg["left_pose"], robot_cfg["speed"])

def go_left_home():
    logger.warning("Moving to left home position")
    mc.send_angles(pcb_273_cfg["left_home"], robot_cfg["speed"])

def go_right():
    logger.warning("Moving to right position")
    mc.send_angles(pcb_273_cfg["right_pose"], robot_cfg["speed"])

def go_right_home():
    logger.warning("Moving to right home position")
    mc.send_angles(pcb_273_cfg["right_home"], robot_cfg["speed"])

def go_before_home():
    logger.warning("Moving to before home position")
    mc.send_angles(robot_cfg["before_home"], robot_cfg["speed"])



# ---------- Main Process ----------
def run_cycle():
    # Wait for trigger and turn on light
    wait_for_trigger()
    tower_light_green_off()
    light_on()

    # Home position to start
    go_home()
    time.sleep(0.1)
        
    # Move to left and capture image    
    go_left()
    time.sleep(0.5)
    left_image_path = capture_image("left")

    go_before_home()    
    # time.sleep(0.1)
    
    # Move to right and capture image
    go_right()
    time.sleep(0.5)
    right_image_path = capture_image("right")

    go_before_home()
    # time.sleep(0.1)

    # Turn off light and return home
    go_home()
    time.sleep(3)
    light_off()
    
    logger.warning("Cycle complete. Images saved: %s, %s", left_image_path, right_image_path)

    return left_image_path, right_image_path



# ---------- Execute Main Loop ----------
if __name__ == "__main__":

    tower_light_red_off()
    tower_light_green_off()
    # tower_light_yellow_off()
    light_off()
    buzzer_off()

    logger.warning("System Ready. Press button to scan PCB.")

    buzzer_on()
    time.sleep(0.5)
    buzzer_off()
    cycle_through_lights()
    

    while True:
        try:

            tower_light_green_on()

            l_img, r_img = run_cycle()

            if l_img and r_img:
                # logger.warning("Cycle Successful. Captured images: Left-> %s, Right-> %s", l_img, r_img)
                print("Captured images:", l_img, r_img)

                tower_light_green_off()
                tower_light_red_on()

            else:
                logger.error("Cycle Failed. Failed to capture one or both images.")

            
            # Wait for board removal
            logger.warning("Waiting for board removal...")
            while not board_removed():
                time.sleep(1)


            logger.warning("Board removed. Ready for next cycle.")
            tower_light_red_off()

        except KeyboardInterrupt:
            logger.warning("Shutting down...")
            go_home()
            mc.power_off()
            break
    
        except Exception as e:
            logger.error("Error during cycle: %s", e)
            #line numberthe error is
            logger.error("Error at line number: %s", e.__traceback__.tb_lineno)


            mc.stop()
            time.sleep(2)

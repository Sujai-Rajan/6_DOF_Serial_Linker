import sys, os
import socket
import json
import time
from typing import Dict, Any, Optional
from enum import IntEnum
from pathlib import Path


class TaskState(IntEnum):
    Pending = 0
    Processing = 1
    Completed = 2
    
class ProcessingServer:
    def __init__(self, host: str = "10.40.17.62", port: int = 9000):
        self.host = host
        self.port = port

    def send_request(self, request_type: str, values: Dict[str, Any] = None, task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a request to the server and return the response as a dictionary.
        """
        if values is None:
            values = {}

        request = {
            "RequestType": request_type,
            "Values": values
        }

        # Attach TaskId if chaining requests
        if task_id:
            request["TaskId"] = task_id

        request_json = json.dumps(request)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.host, self.port))
            s.sendall(request_json.encode("utf-8"))

            response_data = s.recv(4096)
            response_json = response_data.decode("utf-8")
            response = json.loads(response_json)

        return response

    def heartbeat(self) -> Dict[str, Any]:
        """
        Example: Send a heartbeat request to check server availability.
        """
        return self.send_request("Heartbeat")
        
    def submit(self, filename: str) -> Dict[str, Any]:
        """
        Send a submit request with a filename.
        """
        return self.send_request("Submit", values={"FileName": filename})
        
    def get_async_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Send a submit request with a filename.
        """
        return self.send_request("GetAsyncTaskStatus", task_id=task_id)
        
    def cancel_async_task(self, task_id: str) -> Dict[str, Any]:
        """
        Send a submit request with a filename.
        """
        return self.send_request("CancelAsyncTask", task_id=task_id)

    def print_response(self, response: Dict[str, Any]):
        print("Server Response:")
        print(f"  TaskId: {response.get('TaskId')}")
        print(f"  GenericResult: {response.get('GenericResult')}")

        state_value = response.get("State")
        try:
            state_name = TaskState(state_value).name
        except Exception:
            state_name = f"Unknown ({state_value})"
        print(f"  State: {state_name}")

        print(f"  LastStateChange: {response.get('LastStateChange')}")
        print("  Results:")
        for key, value in response.get("Results", {}).items():
            print(f"    {key}: {value}")


# --- Path translation settings ---
SMB_MOUNT = "/mt/barcode_dropbox"       # local Linux mount point
UNC_ROOT  = r"\\hsv-dc2\barcode_reader"  # Windows-visible UNC root

def to_windows_path(path: str) -> str:

    path = os.path.abspath(path)
    if path.startswith(SMB_MOUNT):
        relative = os.path.relpath(path, SMB_MOUNT)
        return UNC_ROOT + "\\" + relative.replace("/", "\\")
    return path  # fallback if not under mount

def process_barcode(argv):
    """
    Submit an image to the remote Dynamsoft ProcessingServer and return the decoded serial string.
    argv = ["script_name", file_path, result_path]
    Returns: serial string (or None on failure)
    """

    if len(argv) < 3:
        print("This function requires arguments: file_path, result_path")
        return None

    file_path = Path(argv[1])
    if not file_path.exists():
        print("Input file not found:", file_path)
        return None
    file_path = str(file_path)
    result_path = Path(argv[2])

    # Convert local Linux path to Windows UNC for server
    win_path = to_windows_path(file_path)
    # print(f"[INFO] Submitting path to server: {win_path}")

    # Initialize a processing server
    server = ProcessingServer()

    # 1 Heartbeat check
    response = server.heartbeat()
    if not response.get("GenericResult", False):
        print("[ERROR] Heartbeat failed — server offline?")
        return None

    # 2 Submit image for decoding
    response = server.submit(win_path)
    # server.print_response(response)
    taskId = response.get("TaskId")

    if not taskId:
        print("[ERROR] No Task ID received from server.")
        return None

    # 3 Poll until task completed
    while True:
        time.sleep(2)
        response = server.get_async_task_status(taskId)
        # server.print_response(response)

        state_val = response.get("State")
        try:
            state = TaskState(state_val)
        except Exception:
            state = None

        if state == TaskState.Completed:
            serials = response.get("Results", {}).get("serials", [])
            if serials:
                result_serial = str(serials[0])
                print(f"[BARCODE_RETRIVING_SERVER]Task completed! Serial: {result_serial}")

                try:
                    with open(result_path, "w") as f:
                        f.write(result_serial)
                except Exception as e:
                    print(f"[WARN] Could not write result file: {e}")

                return result_serial
            else:
                print("[WARN] Completed, but no serials found in result.")
                return None
            

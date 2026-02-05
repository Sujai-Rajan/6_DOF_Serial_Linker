import sys
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
    def __init__(self, host: str = "127.0.0.1", port: int = 9000):
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
        
    def submit(self, filename: str, templatePath: str) -> Dict[str, Any]:
        """
        Send a submit request with a filename.
        """
        return self.send_request("Submit", values={"FileName": filename, "TemplatePath": templatePath})
        
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

if __name__ == "__main__":
    #Validate arguments
    if len(sys.argv) < 4:
        print("This script must be ran with arguments of img_path, result_path, template_path")
        sys.Exit()
    
    #Validate an image path is specified
    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print("Input file may be missing (Using relative?):", file_path)
    file_path = str(file_path)

    #Obtain the desired location to write the results.
    result_path = Path(sys.argv[2])

    #Validate a template path is specified
    template_path = Path(sys.argv[3])
    if not template_path.exists():
        print("Template file may be missing (Using relative?):", template_path)
    template_path = str(template_path)
    
    #Initialize a processing server object to handle requests.
    server = ProcessingServer("10.40.17.62", 9000)

    #First: heartbeat request
    response = server.heartbeat()
    server.print_response(response)
    
    #Make sure heartbeat succeeded.
    if response.get('GenericResult') == False:
        print("\nHeartbeat failed! Server offline?")

    #Submit a photo for processing.
    response = server.submit(file_path, template_path)
    server.print_response(response)
    taskId = response.get('TaskId')
    
    # Check result.
    while True:
        response = server.get_async_task_status(taskId)
        server.print_response(response)

        state_val = response.get("State")
        try:
            state = TaskState(state_val)
        except Exception:
            state = None

        if state == TaskState.Completed:
            print("\nTask completed.")
            result_serial = str(response["Results"]["serials"][0])
            print(result_serial)
            with open(result_path, "w") as f:
                f.write(result_serial)
            break

        time.sleep(2)

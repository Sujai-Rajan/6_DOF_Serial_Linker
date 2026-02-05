import sys
import os
import platform
import logging
from datetime import datetime
from PIL import Image
import csv

from dynamsoft_barcode_reader_bundle import *

logging.basicConfig(level=logging.INFO)

class DynamsoftBarcodeReader:
    def __init__(self):
        # -----------------------
        # 1. License initialization
        # -----------------------
        if platform.system() == 'Windows':
            folder_path = "/tmp/Dynamsoft"
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

        DBR_license = os.environ.get('DBRLicense')
        if not DBR_license:
            # OLD Trial License # DBR_license = "t0083YQEAAGA+AJru0l8dKId9cZ2PNk/bwjpwd9WvWx71Www/kTvtAlbR6qh4N7hlgz570P0mDfAj/e8xPD2R6R1MK2sT4ZiW753Ge2eNKreIAy7zSIc="
            
            # Paste your temp License here
            DBR_license = "t0082YQEAAAsVp4S8dBXRZdUVApQdU/Fms2+xzwSknyoGkHwNyl5103e55Pzbk+W2YEfGgeSkzWcN3AsYBnEKEui+w/51Vrt/3yy8b9aIDKrv3blJxQ=="
        errorCode, errorMsg = LicenseManager.init_license(DBR_license)
        if errorCode not in (EnumErrorCode.EC_OK, EnumErrorCode.EC_LICENSE_WARNING):
            logging.warning("License error: " + errorMsg)

        # -----------------------
        # 2. CaptureVisionRouter initialization
        # -----------------------
        self.cvr = CaptureVisionRouter()
        self.template_path = "C:\\junk\\ReadDPM.json"
        if os.path.exists(self.template_path):
            ec, em = self.cvr.init_settings_from_file(self.template_path)
            if ec != EnumErrorCode.EC_OK:
                logging.warning("Template load error: " + em)
            else:
                print("Template loaded successfully")
        else:
            logging.warning("Template file not found")

    # -----------------------
    # Decode image file
    # -----------------------
    def decode_image(self, img_path):
        wrapped_results = self._decode_with_retry(img_path)
        # Log results to CSV
        self.log_result_to_csv(img_path, wrapped_results)

    # -----------------------
    # Internal decode with retry
    # -----------------------
    def _decode_with_retry(self, img_path):
        results = self.decode_file(img_path)
        if not results:
            # Retry with scaled image
            print("No barcode found. Trying again with rescaling...")
            img = Image.open(img_path)
            img = img.resize((int(img.width * 0.85), int(img.height * 0.85)))
            retry_path = "C:\\junk\\barcode_images\\barcode_scaled.JPG"
            img.save(retry_path)
            results = self.decode_file(retry_path)
        # Write first barcode to txt
        with open("C:\\junk\\barcode_results.txt", "w") as f:
            if results:
                f.write(results[0]["ID"])
                print(results[0]["ID"])
            else:
                f.write("-1")
                print("No barcode found.")
        return results

    # -----------------------
    # Decode file using CVR
    # -----------------------
    def decode_file(self, img_path):
        wrapped_results = []
        try:
            result_array = self.cvr.capture_multi_pages(img_path, "")
            results = result_array.get_results()
            self.wrap_results(wrapped_results, results)
        except Exception as e:
            logging.warning(f"Decoding error: {e}")
        return wrapped_results

    # -----------------------
    # Wrap results for ROI & format
    # -----------------------
    def wrap_results(self, results_list, cvr_results):
        if not cvr_results:
            return
        for page_index, page_result in enumerate(cvr_results):
            barcodes = page_result.get_decoded_barcodes_result()
            if not barcodes or barcodes.get_items() == 0:
                continue
            for barcode in barcodes.get_items():
                result = {
                    "Type": barcode.get_format_string(),
                    "ID": barcode.get_text(),

                }
                results_list.append(result)

    # -----------------------
    # Log results to CSV
    # -----------------------
    def log_result_to_csv(self, img_path, results):
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        if not results:
            row = [img_path, date_str, time_str, "-1", "-1", "-1", "-1"]
            with open('C:\\junk\\results.csv', 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(row)
            return

        for res in results:
            roi = res.get("ROI", {})
            row = [
                img_path,
                date_str,
                time_str,
                res.get("Type", "-1"),
                res.get("ID", "-1"),
                "-1",  # Confidence placeholder
                f"{roi.get('x1', -1)},{roi.get('y1', -1)},{roi.get('x2', -1)},{roi.get('y2', -1)},{roi.get('x3', -1)},{roi.get('y3', -1)},{roi.get('x4', -1)},{roi.get('y4', -1)}"
            ]
            with open('C:\\junk\\results.csv', 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(row)


if __name__ == '__main__':
    reader = DynamsoftBarcodeReader()
    # Delete previous results.txt
    if os.path.exists("C:\\junk\\barcode_results.txt"):
        os.remove("C:\\junk\\barcode_results.txt")

    if len(sys.argv) < 2:
        with open("C:\\junk\\barcode_results.txt", "w") as f:
            f.write("-1")
    else:
        reader.decode_image(sys.argv[1])

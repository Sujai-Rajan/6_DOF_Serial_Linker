import sys
import os
import logging
from datetime import datetime
import csv

from dynamsoft_barcode_reader_bundle import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DynamsoftBarcodeReader:
    def __init__(self, template_path=None):
        """Initialize the Dynamsoft Barcode Reader with hardcoded paths."""
        # -----------------------
        # 1. License initialization
        # -----------------------
        DBR_license = os.environ.get('DBRLicense')
        if not DBR_license:
            DBR_license = "DLS2eyJoYW5kc2hha2VDb2RlIjoiMTA0MTI2MDAxLTEwNDMxNjUyMSIsIm1haW5TZXJ2ZXJVUkwiOiJodHRwczovL21kbHMuZHluYW1zb2Z0b25saW5lLmNvbS8iLCJvcmdhbml6YXRpb25JRCI6IjEwNDEyNjAwMSIsInN0YW5kYnlTZXJ2ZXJVUkwiOiJodHRwczovL3NkbHMuZHluYW1zb2Z0b25saW5lLmNvbS8iLCJjaGVja0NvZGUiOjIwMzM2MTM2NTV9" 
        
        error_code, error_msg = LicenseManager.init_license(DBR_license)
        if error_code not in (EnumErrorCode.EC_OK, EnumErrorCode.EC_LICENSE_WARNING):
            logger.error(f"License error: {error_msg}")
            raise RuntimeError(f"License initialization failed: {error_msg}")

        # -----------------------
        # 2. CaptureVisionRouter initialization
        # -----------------------
        self.cvr = CaptureVisionRouter()
        self.template_path = template_path or "C:\\junk\\ReadDPM.json"
        
        if os.path.exists(self.template_path):
            ec, em = self.cvr.init_settings_from_file(self.template_path)
            if ec != EnumErrorCode.EC_OK:
                logger.error(f"Template load error: {em}")
                raise RuntimeError(f"Template load error: {em}")
            logger.info("Template loaded successfully")
        else:
            logger.error(f"Template file not found: {self.template_path}")
            raise FileNotFoundError(f"Template file not found: {self.template_path}")
        
        # Performance: cache paths
        self.results_csv_path = 'C:\\junk\\results.csv'
        self.barcode_txt_path = 'C:\\junk\\barcode_results.txt'

    # -----------------------
    # Decode image file
    # -----------------------
    def decode_image(self, img_path):
        """Decode a barcode from an image file and log results."""
        results = self.decode_file(img_path)
        self.log_result_to_csv(img_path, results)
        self._write_barcode_result(results)
        return results
    
    def _write_barcode_result(self, results) -> None:
        """Write the first barcode ID to results text file."""
        try:
            barcode_id = results[0]["ID"] if results else "-1"
            with open(self.barcode_txt_path, "w") as f:
                f.write(barcode_id)
            if barcode_id != "-1":
                logger.info(f"Barcode found: {barcode_id}")
            else:
                logger.info("No barcode found.")
        except (IOError, IndexError, KeyError) as e:
            logger.error(f"Failed to write barcode result: {e}")

    # -----------------------
    # Decode file using CVR
    # -----------------------
    def decode_file(self, img_path):
        """Decode a barcode from an image file using CaptureVisionRouter."""
        wrapped_results = []
        try:
            result_array = self.cvr.capture_multi_pages(img_path, "")
            results = result_array.get_results()
            self.wrap_results(wrapped_results, results)
        except (RuntimeError, AttributeError) as e:
            logger.error(f"Error decoding {img_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error decoding {img_path}: {e}", exc_info=True)
        return wrapped_results

    # -----------------------
    # Wrap results for ROI & format
    # -----------------------
    def wrap_results(self, results_list, cvr_results):
        """Extract barcode data from CVR results and format for output."""
        if not cvr_results:
            return
        
        for page_result in cvr_results:
            barcodes = page_result.get_decoded_barcodes_result()
            if not barcodes or barcodes.get_items() == 0:
                continue
            
            for barcode in barcodes.get_items():
                result = {
                    "Type": barcode.get_format_string(),
                    "ID": barcode.get_text(),
                    "ROI": self._extract_roi_coordinates(barcode)
                }
                results_list.append(result)
    
    def _extract_roi_coordinates(self, barcode):
        """Extract ROI coordinates from barcode, with safe defaults."""
        try:
            points = barcode.get_corner_points()
            if points and len(points) >= 4:
                return {
                    'x1': points[0].x, 'y1': points[0].y,
                    'x2': points[1].x, 'y2': points[1].y,
                    'x3': points[2].x, 'y3': points[2].y,
                    'x4': points[3].x, 'y4': points[3].y,
                }
        except Exception as e:
            logger.debug(f"Could not extract ROI coordinates: {e}")
        
        return {
            'x1': -1, 'y1': -1, 'x2': -1, 'y2': -1,
            'x3': -1, 'y3': -1, 'x4': -1, 'y4': -1
        }

    # -----------------------
    # Log results to CSV
    # -----------------------
    def log_result_to_csv(self, img_path, results):
        """Log barcode decoding results to CSV file."""
        # Pre-format timestamp once (avoid recalculation per result)
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        common_prefix = [img_path, date_str, time_str]

        rows = []
        if not results:
            rows.append(common_prefix + ["-1", "-1", "-1", "-1"])
        else:
            for res in results:
                # Efficiently format ROI coordinates
                roi = res.get("ROI", {})
                roi_str = ",".join(str(roi.get(k, -1)) for k in ['x1', 'y1', 'x2', 'y2', 'x3', 'y3', 'x4', 'y4'])
                rows.append(common_prefix + [
                    res.get("Type", "-1"),
                    res.get("ID", "-1"),
                    "-1",
                    roi_str
                ])
        
        # Write all rows at once for better performance
        try:
            with open(self.results_csv_path, 'a', newline='') as f:
                csv.writer(f).writerows(rows)
        except IOError as e:
            logger.error(f"Failed to write results to CSV: {e}")


if __name__ == '__main__':
    try:
        # Get template path from second argument if provided
        template_path = sys.argv[2] if len(sys.argv) > 2 else None
        reader = DynamsoftBarcodeReader(template_path)
        
        # Delete previous results.txt
        if os.path.exists(reader.barcode_txt_path):
            os.remove(reader.barcode_txt_path)

        if len(sys.argv) < 2:
            with open(reader.barcode_txt_path, "w") as f:
                f.write("-1")
        else:
            reader.decode_image(sys.argv[1])
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

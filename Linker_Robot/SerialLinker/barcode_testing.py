# Trial till 30th October
LICENSE_KEY = "t0082YQEAAA6nkK2AAdabLNdX4wzgNaEUsF5+Rv/QMdd1pkDxSrNR4ppViPuu8GvhW/VpHUagxNXD3SpIq2T/QZi4LVSOdX//3qm8d85EovUAwrpLHg=="  # your short key
_READER = None  # global singleton

# --- Dynamsoft Barcode Reader Integration ---
from dynamsoft_barcode_reader_bundle import LicenseManager, CaptureVisionRouter, EnumErrorCode
import os



def get_barcode_reader():
    """
    Initialize and return a shared Dynamsoft CaptureVisionRouter instance.
    Call this once and reuse for multiple decode_file() calls.
    """
    global _READER
    if _READER is None:
        code, msg = LicenseManager.init_license(LICENSE_KEY)
        if code not in (EnumErrorCode.EC_OK, EnumErrorCode.EC_LICENSE_WARNING):
            print(f"[ERROR] License error ({code}): {msg}")
        else:
            print("[INFO] Dynamsoft license activated successfully.")
        _READER = CaptureVisionRouter()
    return _READER


def decode_file(reader, img_path):
    """
    Decode a single image and return a list with at most ONE barcode object.
    The returned object mimics .barcode_text and .barcode_format_string fields.
    """
    if not os.path.exists(img_path):
        print("[WARN] Image not found:", img_path)
        return []

    try:
        result_array = reader.capture_multi_pages(img_path, "")
        pages = result_array.get_results()

        for page in pages:
            barcodes = page.get_decoded_barcodes_result()
            if not barcodes:
                continue

            items = barcodes.get_items()
            if len(items) > 0:
                b = items[0]  # ✅ Only first barcode
                # mimic legacy attributes
                b.barcode_text = b.get_text()
                b.barcode_format_string = b.get_format_string()
                return [b]  # wrap in list to match your existing code structure

    except Exception as e:
        print("[ERROR] Decode failed:", e)

    return []  # none found

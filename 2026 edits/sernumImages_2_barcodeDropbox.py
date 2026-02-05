local_file_path = "C:\\Sernum_Images\\2D_Barcode.JPG"
dropbox_path = "\\\\hsv-dc2\\barcode_reader\\checker_line_1\\image\\cc_checker_1_image.jpg"

import shutil
def copy_file(source_path, destination_path):
    try:
        # Use shutil.copy2 to preserve metadata and ensure fast copying
        shutil.copy2(source_path, destination_path)
        print(f"File copied from {source_path} to {destination_path} successfully.")
    except Exception as e:
        print(f"An error occurred while copying the file: {e}")
if __name__ == "__main__":
    copy_file(local_file_path, dropbox_path)



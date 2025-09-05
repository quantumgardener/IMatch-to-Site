from datetime import timedelta
from pathlib import Path
import logging
import os
import subprocess
import sys
import time

## Clear the full length of any line so that if the new text is shorter
## there are no issues
def clear_line():
    sys.stdout.write('\033[2K\r')  # Clear entire line and return carriage
    sys.stdout.flush()


## Simplify call to clear_line()
def print_clear(text='', end="\n"):
    clear_line()
    print(text, end=end)


## Provide a timed estimate of progress
class ProgressEstimator:
    def __init__(self, total_items):
        self.total_items = total_items
        self.start_time = time.time()
        self.last_update = self.start_time

    def update(self, current_count):
        now = time.time()
        elapsed = now - self.start_time

        if current_count == 0:
            return "Waiting for progress..."

        avg_time_per_item = elapsed / current_count
        remaining_items = self.total_items - current_count
        estimated_remaining = avg_time_per_item * remaining_items

        return str(timedelta(seconds=int(estimated_remaining)))


## Replace filename extension
def replace_extension(filename: str, new_ext: str) -> str:
    """
    Returns the filename with its extension replaced by new_ext.
    If new_ext doesn’t start with a dot, one is prepended.
    """
    p = Path(filename)
    suffix = new_ext if new_ext.startswith('.') else f'.{new_ext}'
    return str(p.with_suffix(suffix))


## Keep image information private and process in parallel
exiftool_public_tag_args = [
    "-xmp:CreateDate",
    "-xmp-photoshop:DateCreated",
    "-xmp-dc:Title",
    "-xmp-dc:Description",
    "-xmp-xmpRights:All",
    "-xmp-xmp:Rights",
    "-xmp-dc:rights",
    "-XMP-photoshop:Country",
    "-XMP-photoshop:State",
    "-XMP-photoshop:City",
    "-XMP-iptcCore:Location",
    "-Make",
    "-Model",
    "-FNumber",
    "-ExposureTime",
    "-FocalLength",
    "-LensModel",
    "-LensMake",
    '-LensInfo',
    "-GPSLatitude",
    "-GPSLatitudeRef",
    "-GPSLongitude",
    "-GPSLongitudeRef",
    "-GPSAltitude",
    "-GPSAltitudeRef",
    "-overwrite_original"
]

exiftool_private_tag_args = [
    "-xmp:CreateDate",
    "-xmp-photoshop:DateCreated",
    "-xmp-dc:Title",
    "-xmp-dc:Description",
    "-xmp-xmpRights:All",
    "-xmp-xmp:Rights",
    "-xmp-dc:rights",
    "-XMP-photoshop:Country",
    "-XMP-photoshop:State",
    "-XMP-photoshop:City",
    "-Make",
    "-Model",
    "-FNumber",
    "-ExposureTime",
    "-FocalLength",
    "-LensModel",
    "-LensMake",
    '-LensInfo',
    "-overwrite_original"
]

def set_metadata(exiftool_tasks):
    with ExifToolSession() as et:    
        for src, tgt, isPrivate in exiftool_tasks:
            try:
                # Sanitize first
                cmd = ['-all=', '-overwrite_original', tgt]
                response = et.send(cmd) 

                # Copy metadata second
                args = exiftool_private_tag_args if isPrivate else exiftool_public_tag_args
                cmd = ['-TagsFromFile', src] + args + [tgt]
                response = et.send(cmd)

                logging.debug(f"[{tgt}] Metadata copied successfully.\n{response.strip()}")
            except Exception as e:
                logging.error(f"Failed to copy metadata to {tgt}: {e}")


class ExifToolSession:
    def __enter__(self):
        self.process = subprocess.Popen(
            [os.path.normpath(r"C:\Program Files\photools.com\imatch6\exiftool.exe"), '-stay_open', 'True', '-@', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        return self

    def send(self, commands):
        block = '\n'.join(commands) + '\n-execute\n'
        self.process.stdin.write(block)
        self.process.stdin.flush()

        output = ''
        while True:
            line = self.process.stdout.readline()
            if line.strip() == '{ready}':
                break
            output += line
        return output

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.process.stdin.write('-stay_open\nFalse\n')
        self.process.stdin.flush()
        self.process.terminate()

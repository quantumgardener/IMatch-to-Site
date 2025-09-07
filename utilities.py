from datetime import timedelta
from pathlib import Path
import logging
import os
import subprocess
import sys
import threading
import time
from tqdm import tqdm

## Clear the full length of any line so that if the new text is shorter
## there are no issues
def clear_line():
    sys.stdout.write('\033[2K\r')  # Clear entire line and return carriage
    sys.stdout.flush()


## Simplify call to clear_line()
def print_clear(text='', end="\n"):
    clear_line()
    print(text, end=end)


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
    "-ISO",
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
    "-ISO",
    "-LensModel",
    "-LensMake",
    '-LensInfo',
    "-overwrite_original"
]

def set_metadata(exiftool_tasks, controller_name):
    with ExifToolSession() as et:
        for src, tgt, isPrivate in (pbar := tqdm(exiftool_tasks)):
            try:
                pbar.set_description(f"{controller_name}: copying metadata")
                args = exiftool_private_tag_args if isPrivate else exiftool_public_tag_args
                cmd = ['-all=', '-overwrite_original' '-TagsFromFile', src] + args + [tgt]
                response = et.send(cmd)
            except Exception as e:
                logging.error(f"Failed to copy metadata to {tgt}: {e}")


class ExifToolSession:
    def __enter__(self):
        self.process = subprocess.Popen(
            [r"C:\Program Files\photools.com\imatch6\exiftool.exe", '-stay_open', 'True', '-@', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        return self

    def _drain_stderr(self):
        for line in iter(self.process.stderr.readline, ''):
            # logging.warning(f"[ExifTool stderr] {line.strip()}")
            pass

    def send(self, commands, timeout=15):
        block = '\n'.join(commands) + '\n-execute\n'
        self.process.stdin.write(block)
        self.process.stdin.flush()

        output = ''
        start = time.time()
        while True:
            if time.time() - start > timeout:
                raise TimeoutError("ExifTool response timed out.")
            line = self.process.stdout.readline()
            if line.strip() == '{ready}':
                break
            output += line
        return output

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.process.stdin.write('-stay_open\nFalse\n')
        self.process.stdin.flush()
        self.process.terminate()


import time
from datetime import timedelta
import sys

def clear_line():
    sys.stdout.write('\033[2K\r')  # Clear entire line and return carriage
    sys.stdout.flush()

def print_clear(text='', end="\n"):
    clear_line()
    print(text, end=end)

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

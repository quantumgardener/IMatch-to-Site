import sys
def clear_line():
    sys.stdout.write('\033[2K\r')  # Clear entire line and return carriage
    sys.stdout.flush()

def print_clear(text='', end="\n"):
    clear_line()
    print(text, end=end)
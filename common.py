import os


class SushiError(Exception):
    pass

def get_extension(path):
    return (os.path.splitext(path)[1]).lower()

def read_all_text(path):
    with open(path) as file:
        return file.read()

def format_time(seconds):
    cs = round(seconds * 100)
    return u'{0}:{1:02d}:{2:02d}.{3:02d}'.format(
            int(cs // 360000),
            int((cs // 6000) % 60),
            int((cs // 100) % 60),
            int(cs % 100))
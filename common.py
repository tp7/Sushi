import os


class SushiError(Exception):
    pass

def get_extension(path):
    return (os.path.splitext(path)[1]).lower()

def format_time(seconds):
    return u'{0}:{1:02d}:{2:02d}.{3:02d}'.format(
            int(seconds // 3600),
            int((seconds // 60) % 60),
            int(seconds % 60),
            int(round((seconds % 1) * 100)))
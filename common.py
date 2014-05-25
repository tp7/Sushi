import os


class SushiError(Exception):
    pass

def get_extension(path):
    return (os.path.splitext(path)[1]).lower()
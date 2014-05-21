import logging
import sys


def parse_scxvid_keyframes(text):
    return [i-3 for i,line in enumerate(text.splitlines()) if line and line[0] == 'i']

def parse_keyframes(path):
    with open(path) as file:
        text = file.read()
    if text.find('# XviD 2pass stat file')>=0:
        frames = parse_scxvid_keyframes(text)
    else:
        logging.critical('Unsupported keyframes type')
        sys.exit(2)
    if 0 not in frames:
        frames.insert(0, 0)
    return frames

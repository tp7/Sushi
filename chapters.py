import re
from common import read_all_text


def parse_times(times):
    result = []
    for t in times:
        hours, minutes, seconds = map(float, t.split(':'))
        result.append(hours * 3600 + minutes * 60 + seconds)

    result.sort()
    if result[0] != 0:
        result.insert(0, 0)
    return result

def get_xml_start_times(path):
    text = read_all_text(path)
    times = re.findall(r'<ChapterTimeStart>(\d+:\d+:\d+\.\d+)</ChapterTimeStart>', text)
    return parse_times(times)


def get_ogm_start_times(path):
    text = read_all_text(path)
    times = re.findall(r'CHAPTER\d+=(\d+:\d+:\d+\.\d+)', text, flags=re.IGNORECASE)
    return parse_times(times)


import re


def parse_times(times):
    result = []
    for t in times:
        hours, minutes, seconds = map(float, t.split(':'))
        result.append(hours * 3600 + minutes * 60 + seconds)

    result = sorted(result)
    if result[0] != 0:
        result.insert(0, 0)
    return result

def get_xml_start_times(path):
    with open(path) as file:
        text = file.read()

    times = re.findall(r'<ChapterTimeStart>(\d+:\d+:\d+\.\d+)</ChapterTimeStart>', text)
    return parse_times(times)


def get_ogm_start_times(path):
    with open(path) as file:
        text = file.read()

    times = re.findall(r'CHAPTER\d+=(\d+:\d+:\d+\.\d+)', text, flags=re.IGNORECASE)
    return parse_times(times)


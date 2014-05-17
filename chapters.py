import re


def get_xml_start_times(path):
    with open(path) as file:
        text = file.read()

    times = re.findall(r'<ChapterTimeStart>(\d+:\d+:\d+\.\d+)</ChapterTimeStart>', text)

    result = []
    for t in times:
        split = t.split(':')
        result.append(int(split[0])*3600+int(split[1])*60+float(split[2]))

    result = sorted(result)
    if result[0] != 0:
        result.insert(0, 0)
    return result

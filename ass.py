import logging
import sys
import os.path
import re
import codecs

class TimeOffset(object):
    time_regex = re.compile(r'(\d+):(\d+):(\d+)\.(\d+)')

    def __init__(self):
        super(TimeOffset, self).__init__()
        self.hours = self.minutes = self.seconds = self.centiseconds = None

    @staticmethod
    def from_seconds(seconds):
        offset = TimeOffset()
        offset.fill_from_seconds(seconds)
        return offset

    @staticmethod
    def from_string(string):
        parsed = TimeOffset.time_regex.search(string)
        offset = TimeOffset()
        offset.hours = int(parsed.group(1))
        offset.minutes = int(parsed.group(2))
        offset.seconds = int(parsed.group(3))
        offset.centiseconds = int(parsed.group(4))
        return offset

    def fill_from_seconds(self, seconds):
        self.centiseconds = int ((seconds % 1) * 100)
        self.seconds = int (seconds % 60)
        self.minutes = int ((seconds // 60) % 60)
        self.hours = int (seconds // 3600)

    def add_seconds(self, offset):
        self.fill_from_seconds(max(self.total_seconds + offset, 0))

    @property
    def total_seconds(self):
        return self.hours * 3600 + self.minutes * 60 + self.seconds + self.centiseconds / 100.0

    def __unicode__(self):
        return u'{0}:{1:02d}:{2:02d}.{3:02d}'.format(self.hours, self.minutes, self.seconds, self.centiseconds)

    def __repr__(self):
        return unicode(self)

    def __eq__(self, other):
        return self.total_seconds == other.total_seconds

class AssEvent(object):
    def __init__(self, text):
        super(AssEvent, self).__init__()
        split = text.split(':', 1)
        self.kind = split[0]
        split = [x.strip() for x in split[1].split(',', 9)]

        self.layer = split[0]
        self.start = TimeOffset.from_string(split[1])
        self.end = TimeOffset.from_string(split[2])
        self.style = split[3]
        self.name = split[4]
        self.margin_left = split[5]
        self.margin_right = split[6]
        self.margin_vertical = split[7]
        self.effect = split[8]
        self.text = split[9]

        self.shift = 0
        self.broken = False
        self.diff = 1

    def mark_broken(self):
        self.broken = True

    def shift_by_seconds(self, seconds):
        self.start.add_seconds(seconds)
        self.end.add_seconds(seconds)

    def apply_shift(self):
        if self.shift:
            self.shift_by_seconds(self.shift)

    def set_shift(self, shift, audio_diff):
        self.shift = shift
        self.diff = audio_diff

    def copy_shift_from(self, other):
        self.broken = other.broken
        self.shift = other.shift
        self.diff = other.diff

    def __unicode__(self):
        return u'{0}: {1},{2},{3},{4},{5},{6},{7},{8},{9},{10}'.format(self.kind, self.layer, self.start,
                                                                      self.end, self.style, self.name,
                                                                      self.margin_left, self.margin_right,
                                                                      self.margin_vertical, self.effect,
                                                                      self.text)

    def __repr__(self):
        return unicode(self)



class AssScript(object):
    def __init__(self, path):
        super(AssScript, self).__init__()
        self.script_info = []
        self.styles = []
        self.events = []
        parse_function = None

        try:
            with codecs.open(path, encoding='utf-8-sig') as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    low = line.lower()
                    if low == u'[script info]':
                        parse_function = self.parse_script_info_line
                    elif low == u'[v4+ styles]':
                        parse_function = self.parse_styles_line
                    elif low == u'[events]':
                        parse_function = self.parse_event_line
                    elif low.startswith(u'format:'):
                        continue # ignore it
                    elif not parse_function:
                        raise RuntimeError("That's some invalid ASS script")
                    else:
                        parse_function(line)
        except IOError:
            logging.critical("Script {0} not found".format(path))
            sys.exit(2)



    def parse_script_info_line(self, line):
        self.script_info.append(line)

    def parse_styles_line(self, line):
        self.styles.append(line)

    def parse_event_line(self, line):
        self.events.append(AssEvent(line))

    def sort_broken(self):
        self.events = sorted(self.events, key=lambda x: x.broken)

    def sort_by_time(self):
        self.events = sorted(self.events, key=lambda x: x.start.total_seconds)

    def save_to_file(self, path):
        # if os.path.exists(path):
        #     raise RuntimeError('File %s already exists' % path)
        lines = []
        if self.script_info:
            lines.append(u'[Script Info]')
            for line in self.script_info:
                lines.append(line)
            lines.append('')

        if self.styles:
            lines.append(u'[V4+ Styles]')
            lines.append(u'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding')
            for line in self.styles:
                lines.append(line)
            lines.append('')

        if self.events:
            lines.append(u'[Events]')
            lines.append(u'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text')
            for line in self.events:
                lines.append(unicode(line))

        with codecs.open(path, encoding='utf-8', mode= 'w') as file:
            file.write(u'\n'.join(lines))
            # print(u'\n'.join(lines))
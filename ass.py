import logging
import sys
import codecs
import os


class TimeOffset(object):
    __slots__ = ['seconds']

    def __init__(self, seconds=None):
        super(TimeOffset, self).__init__()
        self.seconds = seconds

    @staticmethod
    def from_seconds(seconds):
        return TimeOffset(seconds=seconds)

    @staticmethod
    def from_ass_string(string):
        hours, minutes, seconds = map(float, string.split(':'))
        return TimeOffset(hours*3600+minutes*60+seconds)

    @staticmethod
    def from_srt_string(string):
        return TimeOffset.from_ass_string(string.replace(',','.'))

    def add_seconds(self, offset):
        self.seconds += offset

    @property
    def total_seconds(self):
        return self.seconds

    def to_ass_time_string(self):
        return u'{0}:{1:02d}:{2:02d}.{3:02d}'.format(
            int(self.seconds // 3600),
            int((self.seconds // 60) % 60),
            int(self.seconds % 60),
            int(round((self.seconds % 1) * 100)))

    def to_srt_time_string(self):
        return u'{0:02d}:{1:02d}:{2:02d},{3:03d}'.format(
            int(self.seconds // 3600),
            int((self.seconds // 60) % 60),
            int(self.seconds % 60),
            int(round((self.seconds % 1) * 1000)))

    def __unicode__(self):
        return self.to_ass_time_string()

    def __repr__(self):
        return self.to_ass_time_string()

    def __eq__(self, other):
        return self.seconds == other.seconds


class ScriptEventBase(object):
    def __init__(self, start, end):
        super(ScriptEventBase, self).__init__()
        self.shift = 0
        self.broken = False
        self.diff = 1
        self.start = start
        self.end = end

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


class ScriptBase(object):
    def sort_broken(self):
        self.events = sorted(self.events, key=lambda x: x.broken)

    def sort_by_time(self):
        self.events = sorted(self.events, key=lambda x: x.start.total_seconds)


class SrtEvent(ScriptEventBase):
    def __init__(self, text):
        lines = text.split('\n', 2)
        times = lines[1].split('-->')
        start = TimeOffset.from_srt_string(times[0].rstrip())
        end = TimeOffset.from_srt_string(times[1].lstrip())

        super(SrtEvent, self).__init__(start, end)
        self.idx = int(lines[0])
        self.text = lines[2]

    def __unicode__(self):
        return u'{0}\n{1} --> {2}\n{3}'.format(self.idx, self.start.to_srt_time_string(),
                                               self.end.to_srt_time_string(), self.text)


class SrtScript(ScriptBase):
    def __init__(self, path):
        super(SrtScript, self).__init__()
        try:
            with codecs.open(path, encoding='utf-8-sig') as file:
                self.events = [SrtEvent(x) for x in file.read().replace(os.linesep, '\n').split('\n\n') if x]
        except IOError:
            logging.critical("Script {0} not found".format(path))
            sys.exit(2)

    def save_to_file(self, path):
        text = '\n\n'.join(unicode(x) for x in self.events)
        with codecs.open(path, encoding='utf-8', mode= 'w') as file:
            file.write(text)


class AssEvent(ScriptEventBase):
    def __init__(self, text):
        split = text.split(':', 1)
        self.kind = split[0]
        split = [x.strip() for x in split[1].split(',', 9)]

        start = TimeOffset.from_ass_string(split[1])
        end = TimeOffset.from_ass_string(split[2])

        super(AssEvent, self).__init__(start, end)

        self.layer = split[0]
        self.style = split[3]
        self.name = split[4]
        self.margin_left = split[5]
        self.margin_right = split[6]
        self.margin_vertical = split[7]
        self.effect = split[8]
        self.text = split[9]

    def __unicode__(self):
        return u'{0}: {1},{2},{3},{4},{5},{6},{7},{8},{9},{10}'.format(self.kind, self.layer,
                                                                       self.start.to_ass_time_string(),
                                                                       self.end.to_ass_time_string(),
                                                                       self.style, self.name,
                                                                       self.margin_left, self.margin_right,
                                                                       self.margin_vertical, self.effect,
                                                                       self.text)

    def __repr__(self):
        return unicode(self)


class AssScript(ScriptBase):
    def __init__(self, path):
        parse_script_info_line = lambda x: self.script_info.append(x)
        parse_styles_line = lambda x: self.styles.append(x)
        parse_event_line = lambda x: self.events.append(AssEvent(x))

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
                        parse_function = parse_script_info_line
                    elif low == u'[v4+ styles]':
                        parse_function = parse_styles_line
                    elif low == u'[events]':
                        parse_function = parse_event_line
                    elif low.startswith(u'format:'):
                        continue # ignore it
                    elif not parse_function:
                        raise RuntimeError("That's some invalid ASS script")
                    else:
                        parse_function(line)
        except IOError:
            logging.critical("Script {0} not found".format(path))
            sys.exit(2)

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
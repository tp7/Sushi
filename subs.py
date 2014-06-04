import logging
import codecs
import os
from common import SushiError, format_time


def _parse_ass_time(string):
    hours, minutes, seconds = map(float, string.split(':'))
    return hours*3600+minutes*60+seconds

class ScriptEventBase(object):
    def __init__(self, start, end):
        super(ScriptEventBase, self).__init__()
        self._shift = 0
        self.broken = False
        self._diff = 1
        self.start = start
        self.end = end
        self._linked_event = None

    def mark_broken(self):
        self.broken = True

    @property
    def shift(self):
        return self._linked_event.shift if self.linked else self._shift

    @property
    def diff(self):
        return self._linked_event.diff if self.linked else self._diff

    @property
    def duration(self):
        return self.end - self.start

    def apply_shift(self):
        self.start += self.shift
        self.end += self.shift

    def set_group(self, group):
        self.group = group

    def set_shift(self, shift, audio_diff):
        if self.linked:
            self._resolve_link()
        self._shift = shift
        self._diff = audio_diff

    def link_event(self, other):
        self._linked_event = other

    def _resolve_link(self):
        if not self.linked:
            raise Exception('This is a bug')
        self.broken = self._linked_event.broken
        self._shift = self._linked_event.shift
        self._diff = self._linked_event.diff
        self._linked_event = None

    @property
    def linked(self):
        return self._linked_event is not None

    def set_keyframes(self, prev_kf, next_kf):
        self.prev_kf = prev_kf
        self.next_kf = next_kf

    def get_keyframes_distances(self):
        p = None if self.prev_kf is None else self.prev_kf - (self.start + self.shift)
        n = None if self.next_kf is None else self.next_kf - (self.end + self.shift)
        return (p,n)

    def adjust_shift(self, value):
        if self.linked:
            raise Exception('Cannot adjust time of linked events. This is a bug')
        self._shift += value

class ScriptBase(object):
    def sort_by_time(self):
        self.events = sorted(self.events, key=lambda x: x.start)


class SrtEvent(ScriptEventBase):
    def __init__(self, text):
        lines = text.split('\n', 2)
        times = lines[1].split('-->')
        start =  self._parse_srt_time(times[0].rstrip())
        end = self._parse_srt_time(times[1].lstrip())

        super(SrtEvent, self).__init__(start, end)
        self.idx = int(lines[0])
        self.text = lines[2]

    @staticmethod
    def _parse_srt_time(string):
        return _parse_ass_time(string.replace(',','.'))

    def __unicode__(self):
        return u'{0}\n{1} --> {2}\n{3}'.format(self.idx, self._format_time(self.start),
                                               self._format_time(self.end), self.text)

    @staticmethod
    def _format_time(seconds):
        return u'{0:02d}:{1:02d}:{2:02d},{3:03d}'.format(
            int(seconds // 3600),
            int((seconds // 60) % 60),
            int(seconds % 60),
            int(round((seconds % 1) * 1000)))


class SrtScript(ScriptBase):
    def __init__(self, path):
        super(SrtScript, self).__init__()
        try:
            with codecs.open(path, encoding='utf-8-sig') as file:
                self.events = [SrtEvent(x) for x in file.read().replace(os.linesep, '\n').split('\n\n') if x]
        except IOError:
            raise SushiError("Script {0} not found".format(path))

    def save_to_file(self, path):
        text = '\n\n'.join(unicode(x) for x in self.events)
        with codecs.open(path, encoding='utf-8', mode= 'w') as file:
            file.write(text)


class AssEvent(ScriptEventBase):
    def __init__(self, text):
        split = text.split(':', 1)
        self.kind = split[0]
        split = [x.strip() for x in split[1].split(',', 9)]

        start = _parse_ass_time(split[1])
        end = _parse_ass_time(split[2])

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
                                                                       self._format_time(self.start),
                                                                       self._format_time(self.end),
                                                                       self.style, self.name,
                                                                       self.margin_left, self.margin_right,
                                                                       self.margin_vertical, self.effect,
                                                                       self.text)

    @staticmethod
    def _format_time(seconds):
        return format_time(seconds)

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
                        raise SushiError("That's some invalid ASS script")
                    else:
                        parse_function(line)
        except IOError:
            raise SushiError("Script {0} not found".format(path))

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
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
        self._diff = 1
        self.start = start
        self.end = end
        self._linked_event = None
        self._start_shift = 0
        self._end_shift = 0

    @property
    def shift(self):
        return self._linked_event.shift if self.linked else self._shift

    @property
    def diff(self):
        return self._linked_event.diff if self.linked else self._diff

    @property
    def duration(self):
        return self.end - self.start

    @property
    def shifted_end(self):
        return self.end + self.shift + self._end_shift

    @property
    def shifted_start(self):
        return self.start + self.shift + self._start_shift

    def apply_shift(self):
        self.start = self.shifted_start
        self.end = self.shifted_end

    def set_shift(self, shift, audio_diff):
        if self.linked:
            raise Exception('Cannot set shift of a linked event. This is a bug')
        self._shift = shift
        self._diff = audio_diff

    def adjust_additional_shifts(self, start_shift, end_shift):
        if self.linked:
            raise Exception('Cannot apply additional shifts to a linked event. This is a bug')
        self._start_shift += start_shift
        self._end_shift += end_shift

    def _get_link_chain_end(self):
        return self._linked_event._get_link_chain_end() if self.linked else self

    def link_event(self, other):
        if other._get_link_chain_end() is self:
            raise Exception('Circular link detected. This is a bug')
        self._linked_event = other

    def resolve_link(self):
        if not self.linked:
            raise Exception('Cannot resolve unlinked events. This is a bug')
        self._shift = self._linked_event.shift
        self._diff = self._linked_event.diff
        self._linked_event = None

    @property
    def linked(self):
        return self._linked_event is not None

    def adjust_shift(self, value):
        if self.linked:
            raise Exception('Cannot adjust time of linked events. This is a bug')
        self._shift += value

    def __repr__(self):
        return unicode(self)


class ScriptBase(object):
    def sort_by_time(self):
        self.events.sort(key=lambda x: x.start)


class SrtEvent(ScriptEventBase):
    def __init__(self, text):
        parse_time = lambda x: _parse_ass_time(x.replace(',', '.'))

        lines = text.split('\n', 2)
        times = lines[1].split('-->')
        start = parse_time(times[0].rstrip())
        end = parse_time(times[1].lstrip())

        super(SrtEvent, self).__init__(start, end)
        self.idx = int(lines[0])
        self.text = lines[2]
        self.style = None
        self.is_comment = False

    def __unicode__(self):
        return u'{0}\n{1} --> {2}\n{3}'.format(self.idx, self._format_time(self.start),
                                               self._format_time(self.end), self.text)

    @staticmethod
    def _format_time(seconds):
        cs = round(seconds * 1000)
        return u'{0:02d}:{1:02d}:{2:02d},{3:03d}'.format(
            int(cs // 3600000),
            int((cs // 60000) % 60),
            int((cs // 1000) % 60),
            int(cs % 1000))


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
        self.is_comment = self.kind.lower() == 'comment'
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
            lines.extend(self.script_info)
            lines.append('')

        if self.styles:
            lines.append(u'[V4+ Styles]')
            lines.append(u'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding')
            lines.extend(self.styles)
            lines.append('')

        if self.events:
            lines.append(u'[Events]')
            lines.append(u'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text')
            for line in self.events:
                lines.append(unicode(line))

        with codecs.open(path, encoding='utf-8', mode= 'w') as file:
            file.write(unicode(os.linesep).join(lines))
            # print(u'\n'.join(lines))
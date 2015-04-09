import codecs
import os
import re
from collections import OrderedDict
from common import SushiError, format_time, format_srt_time


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

    def get_link_chain_end(self):
        return self._linked_event.get_link_chain_end() if self.linked else self

    def link_event(self, other):
        if other.get_link_chain_end() is self:
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
        return format_srt_time(seconds)


class SrtScript(ScriptBase):
    def __init__(self, events):
        super(SrtScript, self).__init__()
        self.events = events

    @classmethod
    def from_file(cls, path):
        try:
            with codecs.open(path, encoding='utf-8-sig') as script:
                return cls([SrtEvent(x) for x in script.read().replace(os.linesep, '\n').split('\n\n') if x])
        except IOError:
            raise SushiError("Script {0} not found".format(path))

    def save_to_file(self, path):
        text = '\n\n'.join(map(unicode, self.events))
        with codecs.open(path, encoding='utf-8', mode='w') as script:
            script.write(text)


class AssEvent(ScriptEventBase):
    def __init__(self, text):
        self.source_index = 0
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
    def __init__(self, script_info, styles, events, other):
        super(AssScript, self).__init__()
        self.script_info = script_info
        self.styles = styles
        self.events = events
        self.other = other

    @classmethod
    def from_file(cls, path):
        script_info, styles, events = [], [], []
        other_sections = OrderedDict()

        def parse_script_info_line(line):
            if line.startswith(u'Format:'):
                return
            script_info.append(line)

        def parse_styles_line(line):
            if line.startswith(u'Format:'):
                return
            styles.append(line)

        def parse_event_line(line):
            if line.startswith(u'Format:'):
                return
            events.append(AssEvent(line))

        def create_generic_parse(section_name):
            other_sections[section_name] = []
            return lambda x: other_sections[section_name].append(x)

        parse_function = None

        try:
            with codecs.open(path, encoding='utf-8-sig') as script:
                for line_idx, line in enumerate(script):
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
                    elif re.match(r'\[.+?\]', low):
                        parse_function = create_generic_parse(line)
                    elif not parse_function:
                        raise SushiError("That's some invalid ASS script")
                    else:
                        try:
                            parse_function(line)
                        except Exception as e:
                            raise SushiError("That's some invalid ASS script: {0} [line {1}]".format(e.message, line_idx))
        except IOError:
            raise SushiError("Script {0} not found".format(path))
        for idx, event in enumerate(events):
            event.source_index = idx
        return cls(script_info, styles, events, other_sections)

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
            events = sorted(self.events, key=lambda x: x.source_index)
            lines.append(u'[Events]')
            lines.append(u'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text')
            lines.extend(map(unicode, events))

        if self.other:
            for section_name, section_lines in self.other.iteritems():
                lines.append('')
                lines.append(section_name)
                lines.extend(section_lines)

        with codecs.open(path, encoding='utf-8-sig', mode='w') as script:
            script.write(unicode(os.linesep).join(lines))

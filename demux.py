import os
from subprocess import Popen, PIPE
import re
from collections import namedtuple
import logging
import sys
import bisect
from common import SushiError, get_extension

AudioStreamInfo = namedtuple('AudioStreamInfo', ['id', 'info', 'title'])
SubtitlesStreamInfo = namedtuple('SubtitlesStreamInfo', ['id', 'info', 'type', 'title'])
MediaInfo = namedtuple('MediaInfo', ['audio', 'subtitles', 'chapters'])


class FFmpeg(object):
    @staticmethod
    def get_info(path):
        try:
            process = Popen(['ffmpeg', '-hide_banner', '-i', path], stderr=PIPE)
            out, err = process.communicate()
            process.wait()
            return err
        except WindowsError as e:
            if e.winerror == 2:
                raise SushiError("Couldn't invoke ffmpeg, check that it's installed")
            raise

    @staticmethod
    def demux_file(input_path, **kwargs):
        args = ['ffmpeg', '-hide_banner', '-i', input_path, '-y']

        audio_stream = kwargs.get('audio_stream', None)
        audio_path = kwargs.get('audio_path', None)
        audio_rate = kwargs.get('audio_rate', None)
        if audio_stream is not None:
            if audio_path is None:
                raise Exception('Output audio path is not set')
            args.extend(('-map', '0:{0}'.format(audio_stream)))
        if audio_rate:
            args.extend(('-ar', str(audio_rate)))
        args.extend(('-ac', '1', '-acodec', 'pcm_s16le', audio_path))

        script_stream = kwargs.get('script_stream', None)
        script_path = kwargs.get('script_path', None)
        if script_stream is not None:
            if script_path is None:
                raise Exception('Output subtitles path is not set')
            args.extend(('-map', '0:{0}'.format(script_stream)))
            args.append(script_path)
        logging.debug('ffmpeg args: {0}'.format(args))
        try:
            process = Popen(args)
            process.wait()
        except WindowsError as e:
            if e.winerror == 2:
                logging.critical("Couldn't invoke ffmpeg, check that it's installed")
                sys.exit(2)
            raise


    @staticmethod
    def get_audio_streams(info):
        streams = re.findall(r'Stream #0:(\d+).*?Audio:(.*?)\r?\n(?:\s*Metadata:\s*\r?\n\s*title\s*:\s*(.*?)\r?\n)?',
                             info)
        return [AudioStreamInfo(int(x[0]), x[1].strip(), x[2]) for x in streams]


    @staticmethod
    def get_chapters_times(info):
        return map(float, re.findall(r'Chapter #0.\d+: start (\d+\.\d+)', info))


    @staticmethod
    def get_subtitles_streams(info):
        maps = {
            'ssa': '.ass',
            'ass': '.ass',
            'subrip': '.srt'
        }
        sanitize_type = lambda x: maps[x] if x in maps else x

        streams = re.findall(r'Stream #0:(\d+).*?Subtitle:\s*((\w*)\s*?.*?)\r?\n(?:\s*Metadata:\s*\r?\n\s*title\s*:\s*(.*?)\r?\n)?',
                             info)
        return [SubtitlesStreamInfo(int(x[0]), x[1].strip(), sanitize_type(x[2]), x[3].strip()) for x in streams]

    @staticmethod
    def get_fps(info):
        fps = re.findall(r'Stream #0:.*?Video: .*?,\s*([\d\.]+)\s*fps', info)
        if not fps:
            return None
        return float(fps[0])


class Timecodes(object):
    def __init__(self, times, default_fps):
        super(Timecodes, self).__init__()
        self.times = times
        self.default_frame_duration = 1.0 / default_fps if default_fps else None


    def get_frame_time(self, number):
        try:
            return self.times[number]
        except IndexError:
            if not self.default_frame_duration:
                raise Exception("Couldn't determine fps, broken state")
            if self.times:
                return self.times[-1] + (self.default_frame_duration) * (number-len(self.times)+1)
            else:
                return number * self.default_frame_duration

    def get_frame_size(self, timestamp):
        try:
            number = bisect.bisect_left(self.times, timestamp)
        except:
            return self.default_frame_duration

        c = self.get_frame_time(number)

        if number == len(self.times):
            p = self.get_frame_time(number-1)
            return c-p
        else:
            n = self.get_frame_time(number+1)
            return n-c


class CfrTimecodes(object):
    def __init__(self, fps):
        self.frame_duration = 1.0 / fps

    def get_frame_time(self, number):
        return number * self.frame_duration

    def get_frame_size(self, timestamp):
        return self.frame_duration


def timecodes_v1_to_v2(default_fps, overrides):
    # start, end, fps
    overrides = [(int(x[0]), int(x[1]), float(x[2])) for x in overrides]
    if not overrides:
        return []

    fps = [default_fps] * (overrides[-1][1]+1)
    for o in overrides:
        fps[o[0]:o[1]+1] = [o[2]] * (o[1]-o[0]+1)

    v2 = [0]
    for d in (1.0 / f for f in fps):
        v2.append(v2[-1] + d)
    return v2


def parse_timecodes(text):
    lines = text.splitlines()
    if not lines:
        return []
    first = lines[0].lower().lstrip()
    if first.startswith('# timecode format v2'):
        tcs = [float(x) / 1000.0 for x in lines[1:]]
        return Timecodes(tcs, None)
    elif first.startswith('# timecode format v1'):
        default = float(lines[1].lower().replace('assume ', ""))
        overrides = (x.split(',') for x in lines[2:])
        return Timecodes(timecodes_v1_to_v2(default, overrides), default)
    else:
        raise SushiError('This timecodes format is not supported')


def read_timecodes(path):
    with open(path) as file:
        return parse_timecodes(file.read())


def get_media_info(path):
    info = FFmpeg.get_info(path)
    audio_streams = FFmpeg.get_audio_streams(info)
    subs_streams = FFmpeg.get_subtitles_streams(info)
    chapter_times = FFmpeg.get_chapters_times(info)
    return MediaInfo(audio_streams, subs_streams, chapter_times)


class Demuxer(object):
    def __init__(self, path):
        super(Demuxer, self).__init__()
        self._path = path
        self._is_wav = get_extension(self._path) == '.wav'
        self._mi = None if self._is_wav else get_media_info(self._path)
        self._demux_audio = self._demux_subs = self.make_timecodes = self.make_keyframes = False

    @property
    def is_wav(self):
        return self._is_wav

    @property
    def chapters(self):
        if self.is_wav:
            return []
        return self._mi.chapters

    def set_audio(self, stream_idx, output_path, sample_rate):
        self._audio_stream = self._select_stream(self._mi.audio, stream_idx, 'audio')
        self._audio_output_path = output_path
        self._audio_sample_rate = sample_rate
        self._demux_audio = True

    def set_script(self, stream_idx, output_path):
        self._script_stream = self._select_stream(self._mi.subtitles, stream_idx, 'subtitles')
        self._script_output_path = output_path
        self._demux_subs = True

    def get_subs_type(self, stream_idx):
        return self._select_stream(self._mi.subtitles, stream_idx, 'subtitles').type

    def demux(self):
        ffargs = {}
        if self._demux_audio:
            ffargs['audio_stream'] = self._audio_stream.id
            ffargs['audio_path'] = self._audio_output_path
            ffargs['audio_rate'] = self._audio_sample_rate
        if self._demux_subs:
            ffargs['script_stream'] = self._script_stream.id
            ffargs['script_path'] = self._script_output_path

        if ffargs:
            FFmpeg.demux_file(self._path, **ffargs)

    def cleanup(self):
        if self._demux_audio:
            os.remove(self._audio_output_path)
        if self._demux_subs:
            os.remove(self._script_output_path)

    @classmethod
    def _format_streams(cls, streams):
        return '\n'.join('{0}{1}: {2}'.format(s.id, ' (%s)' % s.title if s.title else '', s.info) for s in streams)

    def _select_stream(self, streams, chosen_idx, name):
        if not streams:
            raise SushiError('No {0} streams found in {1}'.format(name, self._path))
        if chosen_idx is None:
            if len(streams) > 1:
                raise SushiError('More than one {0} stream found in {1}.'
                    'You need to specify the exact one to demux. Here are all candidates:\n'
                    '{1}'.format(name, self._path, self._format_streams(self._mi.audio)))
            return streams[0]

        try:
            return next(x for x in self._mi.audio if x.id == chosen_idx)
        except StopIteration:
            raise SushiError("Stream with index {0} doesn't exist in {1}.\n"
                             "Here are all that do:\n"
                             "{2}".format(chosen_idx, self._path, self._format_streams(self._mi.audio)))

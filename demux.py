from subprocess import Popen, PIPE
import re
from collections import namedtuple
import logging
import sys
import bisect

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
                logging.critical("Couldn't invoke ffmpeg, check that it's installed")
                sys.exit(2)
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
        def average(a, b):
            return (a+b)/2.0

        try:
            number = bisect.bisect_left(self.times, timestamp)
        except:
            return self.default_frame_duration

        c = self.get_frame_time(number)

        if number == 0:
            n2 = self.get_frame_time(number+2)
            n1 = self.get_frame_time(number+1)
            return average(n2-n1, n1-c)
        elif number == len(self.times):
            p = self.get_frame_time(number-1)
            p2 = self.get_frame_time(number-2)
            return average(c-p, p-p2)
        else:
            n = self.get_frame_time(number+1)
            p = self.get_frame_time(number-1)
            return average(n-c, c-p)


class CfrTimecodes(object):
    def __init__(self, fps):
        self.fps = fps
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


def read_timecodes(path):
    with open(path) as file:
        lines = file.read().splitlines()
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
        logging.critical('This timecodes format is not supported')
        sys.exit(2)


def get_media_info(path, audio=True, subtitles=True, chapters=True):
    info = FFmpeg.get_info(path)
    audio_streams = FFmpeg.get_audio_streams(info) if audio else None
    subs_streams = FFmpeg.get_subtitles_streams(info) if audio else None
    chapter_times = FFmpeg.get_chapters_times(info) if audio else None
    return MediaInfo(audio_streams, subs_streams, chapter_times)

# t = read_timecodes('J:\\tc2.txt')
# print(t.get_frame_size(1359.66))
# print(t.get_frame_time(4010)  * 1000)

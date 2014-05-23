from subprocess import Popen, PIPE
import re
from collections import namedtuple
import logging
import sys

AudioStreamInfo = namedtuple('AudioStreamInfo', ['id', 'info', 'title'])
SubtitlesStreamInfo = namedtuple('SubtitlesStreamInfo', ['id', 'info', 'type', 'title'])


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

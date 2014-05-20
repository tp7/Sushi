from subprocess import Popen, PIPE
import re
from collections import namedtuple
import logging

AudioStreamInfo = namedtuple('AudioStreamInfo', ['id', 'info', 'title'])
SubtitlesStreamInfo = namedtuple('SubtitlesStreamInfo', ['id', 'info', 'type', 'title'])


class FFmpeg(object):
    @staticmethod
    def get_info(path):
        process = Popen(['ffmpeg', '-hide_banner', '-i', path], stderr=PIPE)
        out, err = process.communicate()
        process.wait()
        return err


    @staticmethod
    def demux_file(input_path, **kwargs):
        acodec = kwargs.get('audio_codec', 'pcm_u8')
        if acodec not in ('pcm_u8', 'pcm_s16le'):
            raise Exception('Invalid audio_codec')

        args = ['ffmpeg', '-hide_banner', '-i', input_path, '-y']

        audio_stream = kwargs.get('audio_stream', None)
        audio_path = kwargs.get('audio_path', None)
        if audio_stream is not None:
            if audio_path is None:
                raise Exception('Output audio path is not set')
            args.extend(('-map', '0:{0}'.format(audio_stream)))
        args.extend(('-ac', '1', '-acodec', acodec, audio_path))

        script_stream = kwargs.get('script_stream', None)
        script_path = kwargs.get('script_path', None)
        if script_stream is not None:
            if script_path is None:
                raise Exception('Output subtitles path is not set')
            args.extend(('-map', '0:{0}'.format(script_stream)))
            args.append(script_path)
        logging.debug('ffmpeg args: {0}'.format(args))
        process = Popen(args)
        process.wait()


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


#
# info = FFmpeg.get_info(r"H:\!Ongoing\[Underwater] Knights of Sidonia - 06 (720p) [8F78C642].mkv")
# subs = FFmpeg.get_subtitles_streams(info)
# print(subs)
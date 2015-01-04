import unittest
import mock

from demux import FFmpeg
from common import SushiError


def create_popen_mock():
    popen_mock = mock.Mock()
    process_mock = mock.Mock()
    process_mock.configure_mock(**{'communicate.return_value': ('ouput', 'error')})
    popen_mock.return_value = process_mock
    return popen_mock


class FFmpegTestCase(unittest.TestCase):
    ffmpeg_output = '''Input #0, matroska,webm, from 'test.mkv':
        Stream #0:0(jpn): Video: h264 (High 10), yuv420p10le, 1280x720 [SAR 1:1 DAR 16:9], 23.98 fps, 23.98 tbr, 1k tbn, 47.95 tbc (default)
        Metadata:
          title           : Video 10bit
        Stream #0:1(jpn): Audio: aac, 48000 Hz, stereo, fltp (default)
        Metadata:
          title           : Audio AAC 2.0
        Stream #0:2(eng): Subtitle: ssa (default)
        Metadata:
          title           : English Subtitles
        .................................'''

    def test_parses_audio_stream(self):
        audio = FFmpeg._get_audio_streams(self.ffmpeg_output)
        self.assertEqual(len(audio), 1)
        self.assertEqual(audio[0].id, 1)
        self.assertEqual(audio[0].title, 'Audio AAC 2.0')

    def test_parses_video_stream(self):
        video = FFmpeg._get_video_streams(self.ffmpeg_output)
        self.assertEqual(len(video), 1)
        self.assertEqual(video[0].id, 0)
        self.assertEqual(video[0].title, 'Video 10bit')

    def test_parses_subtitles_stream(self):
        subs = FFmpeg._get_subtitles_streams(self.ffmpeg_output)
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].id, 2)
        self.assertEqual(subs[0].title, 'English Subtitles')

    @mock.patch('subprocess.Popen', new_callable=create_popen_mock)
    def test_get_info_call_args(self, popen_mock):
        FFmpeg.get_info('random_file.mkv')
        self.assertEquals(popen_mock.call_args[0][0], ['ffmpeg', '-hide_banner', '-i', 'random_file.mkv'])

    @mock.patch('subprocess.Popen', new_callable=create_popen_mock)
    def test_get_info_fail_when_no_mmpeg(self, popen_mock):
        popen_mock.return_value.communicate.side_effect = OSError(2, "ignored")
        self.assertRaises(SushiError, lambda: FFmpeg.get_info('random.mkv'))

    @mock.patch('subprocess.call')
    def test_demux_file_call_args(self, call_mock):
        FFmpeg.demux_file('random.mkv', audio_stream=0, audio_path='audio1.wav')
        FFmpeg.demux_file('random.mkv', audio_stream=0, audio_path='audio2.wav', audio_rate=12000)
        FFmpeg.demux_file('random.mkv', script_stream=0, script_path='subs1.ass')
        FFmpeg.demux_file('random.mkv', video_stream=0, timecodes_path='tcs1.txt')

        FFmpeg.demux_file('random.mkv', audio_stream=1, audio_path='audio0.wav', audio_rate=12000,
                          script_stream=2, script_path='out0.ass', video_stream=0, timecodes_path='tcs0.txt')

        call_mock.assert_any_call(['ffmpeg', '-hide_banner', '-i', 'random.mkv', '-y',
                                   '-map', '0:0', '-ac', '1', '-acodec', 'pcm_s16le', 'audio1.wav'])
        call_mock.assert_any_call(['ffmpeg', '-hide_banner', '-i', 'random.mkv', '-y',
                                   '-map', '0:0', '-ar', '12000', '-ac', '1', '-acodec', 'pcm_s16le', 'audio2.wav'])
        call_mock.assert_any_call(['ffmpeg', '-hide_banner', '-i', 'random.mkv', '-y',
                                   '-map', '0:0', 'subs1.ass'])
        call_mock.assert_any_call(['ffmpeg', '-hide_banner', '-i', 'random.mkv', '-y',
                                   '-map', '0:0', '-f', 'mkvtimestamp_v2', 'tcs1.txt'])
        call_mock.assert_any_call(['ffmpeg', '-hide_banner', '-i', 'random.mkv', '-y',
                                   '-map', '0:1', '-ar', '12000', '-ac', '1', '-acodec', 'pcm_s16le', 'audio0.wav',
                                   '-map', '0:2', 'out0.ass',
                                   '-map', '0:0', '-f', 'mkvtimestamp_v2', 'tcs0.txt'])

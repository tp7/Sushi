import unittest
from demux import FFmpeg


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

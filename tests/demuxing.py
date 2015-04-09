import unittest
import mock

from demux import FFmpeg, MkvToolnix, SCXviD
from common import SushiError
import chapters


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
        Stream #0:1(jpn): Audio: aac, 48000 Hz, stereo, fltp (default) (forced)
        Metadata:
          title           : Audio AAC 2.0
        Stream #0:2(eng): Audio: aac, 48000 Hz, stereo, fltp
        Metadata:
          title           : English Audio AAC 2.0
        Stream #0:3(eng): Subtitle: ssa (default) (forced)
        Metadata:
          title           : English Subtitles
        Stream #0:4(enm): Subtitle: ass
        Metadata:
          title           : English (JP honorifics)
        .................................'''

    def test_parses_audio_stream(self):
        audio = FFmpeg._get_audio_streams(self.ffmpeg_output)
        self.assertEqual(len(audio), 2)
        self.assertEqual(audio[0].id, 1)
        self.assertEqual(audio[0].title, 'Audio AAC 2.0')
        self.assertEqual(audio[1].id, 2)
        self.assertEqual(audio[1].title, 'English Audio AAC 2.0')

    def test_parses_video_stream(self):
        video = FFmpeg._get_video_streams(self.ffmpeg_output)
        self.assertEqual(len(video), 1)
        self.assertEqual(video[0].id, 0)
        self.assertEqual(video[0].title, 'Video 10bit')

    def test_parses_subtitles_stream(self):
        subs = FFmpeg._get_subtitles_streams(self.ffmpeg_output)
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0].id, 3)
        self.assertTrue(subs[0].default)
        self.assertEqual(subs[0].title, 'English Subtitles')
        self.assertEqual(subs[1].id, 4)
        self.assertFalse(subs[1].default)
        self.assertEqual(subs[1].title, 'English (JP honorifics)')

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


class MkvExtractTestCase(unittest.TestCase):
    @mock.patch('subprocess.call')
    def test_extract_timecodes(self, call_mock):
        MkvToolnix.extract_timecodes('video.mkv', 1, 'timecodes.tsc')
        call_mock.assert_called_once_with(['mkvextract', 'timecodes_v2', 'video.mkv', '1:timecodes.tsc'])


class SCXviDTestCase(unittest.TestCase):
    @mock.patch('subprocess.Popen')
    def test_make_keyframes(self, popen_mock):
        SCXviD.make_keyframes('video.mkv', 'keyframes.txt')
        self.assertTrue('ffmpeg' in (x.lower() for x in popen_mock.call_args_list[0][0][0]))
        self.assertTrue('scxvid' in (x.lower() for x in popen_mock.call_args_list[1][0][0]))

    @mock.patch('subprocess.Popen')
    def test_no_ffmpeg(self, popen_mock):
        def raise_no_app(cmd_args, **kwargs):
            if 'ffmpeg' in (x.lower() for x in cmd_args):
                raise OSError(2, 'ignored')

        popen_mock.side_effect = raise_no_app
        self.assertRaisesRegexp(SushiError, '[fF][fF][mM][pP][eE][gG]',
                                lambda: SCXviD.make_keyframes('video.mkv', 'keyframes.txt'))

    @mock.patch('subprocess.Popen')
    def test_no_scxvid(self, popen_mock):
        def raise_no_app(cmd_args, **kwargs):
            if 'scxvid' in (x.lower() for x in cmd_args):
                raise OSError(2, 'ignored')
            return mock.Mock()

        popen_mock.side_effect = raise_no_app
        self.assertRaisesRegexp(SushiError, '[sS][cC][xX][vV][iI][dD]',
                                lambda: SCXviD.make_keyframes('video.mkv', 'keyframes.txt'))


class ExternalChaptersTestCase(unittest.TestCase):
    def test_parse_xml_start_times(self):
        file_text = """<?xml version="1.0"?>
<!-- <!DOCTYPE Chapters SYSTEM "matroskachapters.dtd"> -->
<Chapters>
  <EditionEntry>
    <EditionUID>2092209815</EditionUID>
    <ChapterAtom>
      <ChapterUID>3122448259</ChapterUID>
      <ChapterTimeStart>00:00:00.000000000</ChapterTimeStart>
      <ChapterDisplay>
        <ChapterString>Prologue</ChapterString>
      </ChapterDisplay>
    </ChapterAtom>
    <ChapterAtom>
      <ChapterUID>998777246</ChapterUID>
      <ChapterTimeStart>00:00:17.017000000</ChapterTimeStart>
      <ChapterDisplay>
        <ChapterString>Opening Song ("YES!")</ChapterString>
      </ChapterDisplay>
    </ChapterAtom>
    <ChapterAtom>
      <ChapterUID>55571857</ChapterUID>
      <ChapterTimeStart>00:01:47.023000000</ChapterTimeStart>
      <ChapterDisplay>
        <ChapterString>Part A (Tale of the Doggypus)</ChapterString>
      </ChapterDisplay>
    </ChapterAtom>
  </EditionEntry>
</Chapters>
"""
        parsed_times = chapters.parse_xml_start_times(file_text)
        self.assertEqual(parsed_times, [0, 17.017, 107.023])

    def test_parse_ogm_start_times(self):
        file_text = """CHAPTER01=00:00:00.000
CHAPTER01NAME=Prologue
CHAPTER02=00:00:17.017
CHAPTER02NAME=Opening Song ("YES!")
CHAPTER03=00:01:47.023
CHAPTER03NAME=Part A (Tale of the Doggypus)
"""
        parsed_times = chapters.parse_ogm_start_times(file_text)
        self.assertEqual(parsed_times, [0, 17.017, 107.023])

    def test_format_ogm_chapters(self):
        chapters_text = chapters.format_ogm_chapters(start_times=[0, 17.017, 107.023])
        self.assertEqual(chapters_text, """CHAPTER01=00:00:00.000
CHAPTER01NAME=
CHAPTER02=00:00:17.017
CHAPTER02NAME=
CHAPTER03=00:01:47.023
CHAPTER03NAME=
""")

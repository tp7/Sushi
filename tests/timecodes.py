import unittest
from demux import Timecodes


class CfrTimecodesTestCase(unittest.TestCase):
    def test_get_frame_time_zero(self):
        tcs = Timecodes.cfr(23.976)
        t = tcs.get_frame_time(0)
        self.assertEqual(t, 0)

    def test_get_frame_time_sane(self):
        tcs = Timecodes.cfr(23.976)
        t = tcs.get_frame_time(10)
        self.assertAlmostEqual(10.0/23.976, t)

    def test_get_frame_time_insane(self):
        tcs = Timecodes.cfr(23.976)
        t = tcs.get_frame_time(100000)
        self.assertAlmostEqual(100000.0/23.976, t)

    def test_get_frame_size(self):
        tcs = Timecodes.cfr(23.976)
        t1 = tcs.get_frame_size(0)
        t2 = tcs.get_frame_size(1000)
        self.assertAlmostEqual(1.0/23.976, t1)
        self.assertAlmostEqual(t1, t2)

    def test_get_frame_number(self):
        tcs = Timecodes.cfr(24000.0/1001.0)
        self.assertEqual(tcs.get_frame_number(0), 0)
        self.assertEqual(tcs.get_frame_number(1145.353), 27461)
        self.assertEqual(tcs.get_frame_number(1001.0/24000.0 * 1234567), 1234567)


class TimecodesTestCase(unittest.TestCase):
    def test_cfr_timecodes_v2(self):
        text = '# timecode format v2\n' + '\n'.join(str(1000 * x / 23.976) for x in range(0, 30000))
        parsed = Timecodes.parse(text)

        self.assertAlmostEqual(1.0/23.976, parsed.get_frame_size(0))
        self.assertAlmostEqual(1.0/23.976, parsed.get_frame_size(25))
        self.assertAlmostEqual(1.0/23.976*100, parsed.get_frame_time(100))
        self.assertEqual(0, parsed.get_frame_time(0))
        self.assertEqual(0, parsed.get_frame_number(0))
        self.assertEqual(27461, parsed.get_frame_number(1145.353))

    def test_cfr_timecodes_v1(self):
        text = '# timecode format v1\nAssume 23.976024'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(1.0/23.976024, parsed.get_frame_size(0))
        self.assertAlmostEqual(1.0/23.976024, parsed.get_frame_size(25))
        self.assertAlmostEqual(1.0/23.976024*100, parsed.get_frame_time(100))
        self.assertEqual(0, parsed.get_frame_time(0))
        self.assertEqual(0, parsed.get_frame_number(0))
        self.assertEqual(27461, parsed.get_frame_number(1145.353))

    def test_cfr_timecodes_v1_with_overrides(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,23.976000\n3000,5000,23.976000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(1.0/23.976, parsed.get_frame_size(0))
        self.assertAlmostEqual(1.0/23.976, parsed.get_frame_size(25))
        self.assertAlmostEqual(1.0/23.976*100, parsed.get_frame_time(100))
        self.assertEqual(0, parsed.get_frame_time(0))

    def test_vfr_timecodes_v1_frame_size_at_first_frame(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,29.970000\n3000,4000,59.940000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(1.0/29.97, parsed.get_frame_size(timestamp=0))

    def test_vfr_timecodes_v1_frame_size_outside_of_defined_range(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,29.970000\n3000,4000,59.940000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(1.0/23.976, parsed.get_frame_size(timestamp=5000.0))

    def test_vft_timecodes_v1_frame_size_inside_override_block(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,29.970000\n3000,4000,59.940000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(1.0/29.97, parsed.get_frame_size(timestamp=49.983))

    def test_vft_timecodes_v1_frame_size_between_override_blocks(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,29.970000\n3000,4000,59.940000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(1.0/23.976, parsed.get_frame_size(timestamp=87.496))

    def test_vfr_timecodes_v1_frame_time_at_first_frame(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,29.970000\n3000,4000,59.940000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(0, parsed.get_frame_time(number=0))

    def test_vfr_timecodes_v1_frame_time_outside_of_defined_range(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,29.970000\n3000,4000,59.940000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(1000.968, parsed.get_frame_time(number=25000), places=3)

    def test_vft_timecodes_v1_frame_time_inside_override_block(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,29.970000\n3000,4000,59.940000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(50.05, parsed.get_frame_time(number=1500), places=3)

    def test_vft_timecodes_v1_frame_time_between_override_blocks(self):
        text = '# timecode format v1\nAssume 23.976000\n0,2000,29.970000\n3000,4000,59.940000'
        parsed = Timecodes.parse(text)
        self.assertAlmostEqual(87.579, parsed.get_frame_time(number=2500), places=3)



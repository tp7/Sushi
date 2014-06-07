from collections import namedtuple
import os
import re
import unittest
from mock import patch, ANY
from common import SushiError, format_time
from sushi import parse_args_and_run, detect_groups, interpolate_zeroes, get_distance_to_closest_kf, fix_near_borders, \
    running_median, smooth_events

here = os.path.dirname(os.path.abspath(__file__))

class FakeEvent(object):
    def __init__(self, shift=0.0, diff=0.0):
        self.shift = shift
        self.linked = None
        self.diff = diff

    def set_shift(self, shift, diff):
        self.shift = shift
        self.diff = diff

    def link_event(self, other):
        self.linked = other

    def __repr__(self):
        return repr(self.shift)

@patch('sushi.check_file_exists')
class MainScriptTestCase(unittest.TestCase):
    @staticmethod
    def any_case_regex(text):
        return re.compile(text, flags=re.IGNORECASE)

    def test_checks_that_files_exist(self, mock_object):
        keys = ['--dst', 'dst', '--src', 'src', '--script', 'script', '--chapters', 'chapters',
                '--dst-keyframes', 'dst-keyframes', '--src-keyframes', 'src-keyframes',
                '--src-timecodes', 'src-tcs', '--dst-timecodes', 'dst-tcs']
        try:
            parse_args_and_run(keys)
        except SushiError:
            pass
        mock_object.assert_any_call('src', ANY)
        mock_object.assert_any_call('dst', ANY)
        mock_object.assert_any_call('script', ANY)
        mock_object.assert_any_call('chapters', ANY)
        mock_object.assert_any_call('dst-keyframes', ANY)
        mock_object.assert_any_call('src-keyframes', ANY)
        mock_object.assert_any_call('dst-tcs', ANY)
        mock_object.assert_any_call('src-tcs', ANY)

    def test_raises_on_unknown_script_type(self, ignore):
        keys = ['--src', 's.wav', '--dst', 'd.wav', '--script', 's.mp4']
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'script.*type'), lambda: parse_args_and_run(keys))

    def test_raises_on_script_type_not_matching(self, ignore):
        keys = ['--src', 's.wav', '--dst', 'd.wav', '--script', 's.ass', '-o', 'd.srt']
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'script.*type.*match'), lambda: parse_args_and_run(keys))

    def test_raises_on_timecodes_and_fps_being_defined_together(self, ignore):
        keys = ['--src', 's.wav', '--dst', 'd.wav', '--script', 's.ass', '--src-timecodes', 'tc.txt', '--src-fps', '25']
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'timecodes'), lambda: parse_args_and_run(keys))


class GroupSplittingTestCase(unittest.TestCase):
    def event(self, shift):
        return FakeEvent(shift)

    def test_splits_three_simple_groups(self):
        events = [self.event(0.5)] * 3 + [self.event(1.0)] * 10 + [self.event(0.5)]*5
        groups = detect_groups(events, min_group_size=1)
        self.assertEqual(3, len(groups[0]))
        self.assertEqual(10, len(groups[1]))
        self.assertEqual(5, len(groups[2]))

    def test_single_group_for_all_events(self):
        events = [self.event(0.5)] * 10
        groups = detect_groups(events, min_group_size=1)
        self.assertEqual(10, len(groups[0]))

    def test_merges_small_groups_with_closest_large(self):
        events = [self.event(0.5)]*10 + [self.event(0.8)] + [self.event(1.0)] * 10
        groups = detect_groups(events, min_group_size=5)
        self.assertEqual(10, len(groups[0]))
        self.assertEqual(11, len(groups[1]))

    def test_merges_two_consecutive_small_groups_with_closest_large(self):
        events = [self.event(0.5)]*20 + [self.event(0.9)]*10 + [self.event(0.7)]*10 + [self.event(1.0)] * 20
        groups = detect_groups(events, min_group_size=15)
        self.assertEqual(20, len(groups[0]))
        self.assertEqual(40, len(groups[1]))

    def test_merges_small_first_group_property(self):
        events = [self.event(0.5)] + [self.event(10)] * 10 + [self.event(5)] * 10
        groups = detect_groups(events, min_group_size=5)
        self.assertEqual(11, len(groups[0]))
        self.assertEqual(10, len(groups[1]))

    def test_merges_small_last_group_property(self):
        events = [self.event(0.5)]*10 + [self.event(10)] * 10 + [self.event(5)]
        groups = detect_groups(events, min_group_size=5)
        self.assertEqual(10, len(groups[0]))
        self.assertEqual(11, len(groups[1]))

    def test_does_nothing_when_there_is_only_wrong_groups(self):
        events = [self.event(0.5)]*2 + [self.event(10)] * 3
        groups = detect_groups(events, min_group_size=5)
        self.assertEqual(2, len(groups[0]))
        self.assertEqual(3, len(groups[1]))


class FormatTimeTestCase(unittest.TestCase):
    def test_format_time_zero(self):
        self.assertEqual('0:00:00.00', format_time(0))

    def test_format_time_65_seconds(self):
        self.assertEqual('0:01:05.00', format_time(65))

    def test_format_time_float_seconds(self):
        self.assertEqual('0:00:05.56', format_time(5.559))

    def test_format_time_hours(self):
        self.assertEqual('1:15:35.15', format_time(3600 + 60*15 + 35.15))

    def test_format_100ms(self):
        self.assertEqual('0:09:05.00', format_time(544.997))


class InterpolationTestCase(unittest.TestCase):
    def test_returns_empty_array_when_passed_empty_array(self):
        self.assertEquals(interpolate_zeroes([]), [])

    def test_returns_false_when_no_valid_points(self):
        self.assertFalse(interpolate_zeroes([None, 0, 0, None]))

    def test_returns_full_array_when_no_zeroes(self):
        self.assertEqual(interpolate_zeroes([1,2,3]), [1,2,3])

    def test_interpolates_simple_zeroes(self):
        self.assertEqual(interpolate_zeroes([1,0,3,0,5]), [1,2,3,4,5])

    def test_interpolates_multiple_adjacent_zeroes(self):
        self.assertEqual(interpolate_zeroes([1,0,0,0,5]), [1,2,3,4,5])

    def test_copies_values_to_borders(self):
        self.assertEqual(interpolate_zeroes([0,0,2,0,0]), [2,2,2,2,2])


class RunningMedianTestCase(unittest.TestCase):
    def test_does_no_touch_border_values(self):
        shifts = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        smooth = running_median(shifts, 5)
        self.assertEqual(shifts, smooth)

    def test_removes_broken_values(self):
        shifts = [0.1, 0.1, 0.1, 9001, 0.1, 0.1, 0.1]
        smooth = running_median(shifts, 5)
        self.assertEqual(smooth, [0.1] * 7)


class EventSmoothingTestCase(unittest.TestCase):
    def test_smooths_events_shifts(self):
        events = [FakeEvent(x) for x in (0.1, 0.1, 0.1, 9001, 7777, 0.1, 0.1, 0.1)]
        smooth_events(events, 7)
        self.assertEqual([x.shift for x in events], [0.1]*8)

    def test_keeps_diff_values(self):
        events = [FakeEvent(x, diff=x) for x in (0.1, 0.1, 0.1, 9001, 7777, 0.1, 0.1, 0.1)]
        diffs = [x.diff for x in events]
        smooth_events(events, 7)
        self.assertEqual([x.diff for x in events], diffs)


class BorderFixingTestCase(unittest.TestCase):
    def test_propagates_last_correct_shift_to_broken_events(self):
        events = [FakeEvent(diff=x) for x in (0.9, 0.9, 1.0, 0.4, 0.5, 0.4, 0.3, 0.9, 1.0)]
        fix_near_borders(events, 0.6)
        sf = events[3]
        sl = events[-3]
        self.assertEqual([x.linked for x in events], [sf, sf, sf, None, None, None, None, sl, sl])

    def test_returns_array_with_no_correct_events_unchanged(self):
        events = [FakeEvent(diff=x) for x in (0.9, 0.9, 0.9, 1.0, 0.9)]
        fix_near_borders(events, 0.6)
        self.assertEqual([x.linked for x in events], [None, None, None, None, None])


class ClosestKeyframeDistanceTestCase(unittest.TestCase):
    KEYTIMES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

    def test_finds_correct_distance_to_first_keyframe(self):
        self.assertEqual(get_distance_to_closest_kf(0, self.KEYTIMES), 0)

    def test_finds_correct_distance_to_last_keyframe(self):
        self.assertEqual(get_distance_to_closest_kf(105, self.KEYTIMES), -5)

    def test_finds_correct_distance_to_keyframe_before(self):
        self.assertEqual(get_distance_to_closest_kf(63, self.KEYTIMES), -3)

    def test_finds_distance_to_keyframe_after(self):
        self.assertEqual(get_distance_to_closest_kf(36, self.KEYTIMES), 4)

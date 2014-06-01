import os
import re
import unittest
from mock import patch, ANY
from common import SushiError
from sushi import parse_args_and_run, detect_groups

here = os.path.dirname(os.path.abspath(__file__))

def media(name):
    return here + '/media/' + name

@patch('sushi.check_file_exists')
class MainScriptTestCase(unittest.TestCase):
    @staticmethod
    def any_case_regex(text):
        return re.compile(text, flags=re.IGNORECASE)

    def test_checks_that_files_exist(self, mock_object):
        keys = ['--dst', 'dst', '--src', 'src', '--script', 'script', '--chapters', 'chapters',
                '--keyframes', 'keyframes', '--timecodes', 'tcs']
        try:
            parse_args_and_run(keys)
        except SushiError:
            pass
        mock_object.assert_any_call('src', ANY)
        mock_object.assert_any_call('dst', ANY)
        mock_object.assert_any_call('script', ANY)
        mock_object.assert_any_call('chapters', ANY)
        mock_object.assert_any_call('keyframes', ANY)
        mock_object.assert_any_call('tcs', ANY)

    def test_raises_on_unknown_script_type(self, ignore):
        keys = ['--src', 's.wav', '--dst', 'd.wav', '--script', 's.mp4']
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'script.*type'), lambda: parse_args_and_run(keys))

    def test_raises_on_script_type_not_matching(self, ignore):
        keys = ['--src', 's.wav', '--dst', 'd.wav', '--script', 's.ass', '-o', 'd.srt']
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'script.*type.*match'), lambda: parse_args_and_run(keys))

    def test_raises_on_timecodes_and_fps_being_defined_together(self, ignore):
        keys = ['--src', 's.wav', '--dst', 'd.wav', '--script', 's.ass', '--timecodes', 'tc.txt', '--fps', '25']
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'timecodes'), lambda: parse_args_and_run(keys))


class GroupSplittingTestCase(unittest.TestCase):
    class FakeEvent(object):
        def __init__(self, shift):
            self.shift = shift
            self.linked = False
            self.diff = 0

        def set_shift(self, shift, diff):
            self.shift = shift

        def __repr__(self):
            return repr(self.shift)

    def event(self, shift):
        return self.FakeEvent(shift)

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

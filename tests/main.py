from collections import namedtuple
import os
import re
import unittest
from common import SushiError
from sushi import parse_args_and_run, detect_groups

here = os.path.dirname(os.path.abspath(__file__))

def media(name):
    return here + '/media/' + name


class MainScriptTestCase(unittest.TestCase):
    @staticmethod
    def get_nichibros():
        return ['--src', media('nichibros.m4a'),
                '--dst', media('nichibros-shifted.m4a'),
                '--script', media('nichibros.ass')]

    @staticmethod
    def any_case_regex(text):
        return re.compile(text, flags=re.IGNORECASE)

    def test_raises_on_source_not_existing(self):
        keys = ['--src', 'this_totally_does_not_exist_nKWDBN8rUw65QxcCxVnpcMwH5gFy65', '--dst', media('nichibros-shifted.m4a')]
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'source.*exist'), lambda: parse_args_and_run(keys))

    def test_raises_on_destination_not_existing(self):
        keys = ['--dst', 'this_totally_does_not_exist_nKWDBN8rUw65QxcCxVnpcMwH5gFy65', '--src', media('nichibros.m4a')]
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'dest.*exist'), lambda: parse_args_and_run(keys))

    def test_raises_on_script_not_existing(self):
        keys = ['--src', media('nichibros.m4a'), '--dst', media('nichibros-shifted.m4a'), '--script', media('nKWDBN8rUw65QxcCxVnpcMwH5gFy65')]
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'script.*exist'), lambda: parse_args_and_run(keys))

    def test_raises_on_unknown_script_type(self):
        keys = ['--src', media('nichibros.m4a'), '--dst', media('nichibros-shifted.m4a'), '--script', media('nichibros.m4a')]
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'script.*type'), lambda: parse_args_and_run(keys))

    def test_raises_on_script_type_not_matching(self):
        keys = ['--src', media('nichibros.m4a'), '--dst', media('nichibros-shifted.m4a'), '--script', media('nichibros.ass'), '-o', 'nichibros.srt']
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'script.*type.*match'), lambda: parse_args_and_run(keys))

    def test_raises_on_keyframes_not_existing(self):
        keys = self.get_nichibros()
        keys.extend(['--keyframes', 'this_totally_does_not_exist_nKWDBN8rUw65QxcCxVnpcMwH5gFy65'])
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'keyframes.*exist'), lambda: parse_args_and_run(keys))

    def test_raises_on_chapters_not_existing(self):
        keys = self.get_nichibros()
        keys.extend(['--chapters', 'this_totally_does_not_exist_nKWDBN8rUw65QxcCxVnpcMwH5gFy65'])
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'chapters.*exist'), lambda: parse_args_and_run(keys))

    def test_raises_on_timecodes_not_existing(self):
        keys = self.get_nichibros()
        keys.extend(['--timecodes', 'this_totally_does_not_exist_nKWDBN8rUw65QxcCxVnpcMwH5gFy65'])
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'timecode'), lambda: parse_args_and_run(keys))

    def test_raises_on_timecodes_and_fps_being_defined_together(self):
        keys = self.get_nichibros()
        keys.extend(['--timecodes',  media('nichibros.tc.txt'), '--fps', '23.976'])
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'timecodes'), lambda: parse_args_and_run(keys))


class GroupSplittingTestCase(unittest.TestCase):
    class FakeEvent(object):
        def __init__(self, shift):
            self.shift = shift

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

    def test_merges_small_groups_with_closest_large_skipping_wrong_groups(self):
        events = [self.event(0.5)]*10 + [self.event(0.8)] + [self.event(0.9)]*2 + [self.event(1.0)] * 10
        groups = detect_groups(events, min_group_size=3)
        self.assertEqual(10, len(groups[0]))
        self.assertEqual(13, len(groups[1]))

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

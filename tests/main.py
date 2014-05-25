import os
import re
import unittest
from common import SushiError
from sushi import parse_args_and_run

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

    def test_raises_on_timecodes_not_existing(self):
        keys = self.get_nichibros()
        keys.extend(['--timecodes', 'this_totally_does_not_exist_nKWDBN8rUw65QxcCxVnpcMwH5gFy65'])
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'timecode'), lambda: parse_args_and_run(keys))

    def test_raises_on_timecodes_and_fps_being_defined_together(self):
        keys = self.get_nichibros()
        keys.extend(['--timecodes',  media('nichibros.tc.txt'), '--fps', '23.976'])
        self.assertRaisesRegexp(SushiError, self.any_case_regex(r'timecodes'), lambda: parse_args_and_run(keys))

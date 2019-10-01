import unittest
import tempfile
import os
import codecs

from sushi.subs import AssEvent, AssScript, SrtEvent, SrtScript

SINGLE_LINE_SRT_EVENT = """1
00:14:21,960 --> 00:14:22,960
HOW DID IT END UP LIKE THIS?"""

MULTILINE_SRT_EVENT = """2
00:13:12,140 --> 00:13:14,100
APPEARANCE!
Appearrance (teisai)!
No wait, you're the worst (saitei)!"""

ASS_EVENT = r"Dialogue: 0,0:18:50.98,0:18:55.28,Default,,0,0,0,,Are you trying to (ouch) crush it (ouch)\N like a (ouch) vise (ouch, ouch)?"

ASS_COMMENT = r"Comment: 0,0:18:09.15,0:18:10.36,Default,,0,0,0,,I DON'T GET IT TOO WELL."


class SrtEventTestCase(unittest.TestCase):
    def test_simple_parsing(self):
        event = SrtEvent.from_string(SINGLE_LINE_SRT_EVENT)
        self.assertEqual(14*60+21.960, event.start)
        self.assertEqual(14*60+22.960, event.end)
        self.assertEqual("HOW DID IT END UP LIKE THIS?", event.text)

    def test_multi_line_event_parsing(self):
        event = SrtEvent.from_string(MULTILINE_SRT_EVENT)
        self.assertEqual(13*60+12.140, event.start)
        self.assertEqual(13*60+14.100, event.end)
        self.assertEqual("APPEARANCE!\nAppearrance (teisai)!\nNo wait, you're the worst (saitei)!", event.text)

    def test_parsing_and_printing(self):
        self.assertEqual(SINGLE_LINE_SRT_EVENT, str(SrtEvent.from_string(SINGLE_LINE_SRT_EVENT)))
        self.assertEqual(MULTILINE_SRT_EVENT, str(SrtEvent.from_string(MULTILINE_SRT_EVENT)))


class AssEventTestCase(unittest.TestCase):
    def test_simple_parsing(self):
        event = AssEvent(ASS_EVENT)
        self.assertFalse(event.is_comment)
        self.assertEqual("Dialogue", event.kind)
        self.assertEqual(18*60+50.98, event.start)
        self.assertEqual(18*60+55.28, event.end)
        self.assertEqual("0", event.layer)
        self.assertEqual("Default", event.style)
        self.assertEqual("", event.name)
        self.assertEqual("0", event.margin_left)
        self.assertEqual("0", event.margin_right)
        self.assertEqual("0", event.margin_vertical)
        self.assertEqual("", event.effect)
        self.assertEqual("Are you trying to (ouch) crush it (ouch)\N like a (ouch) vise (ouch, ouch)?", event.text)

    def test_comment_parsing(self):
        event = AssEvent(ASS_COMMENT)
        self.assertTrue(event.is_comment)
        self.assertEqual("Comment", event.kind)

    def test_parsing_and_printing(self):
        self.assertEqual(ASS_EVENT, str(AssEvent(ASS_EVENT)))
        self.assertEqual(ASS_COMMENT, str(AssEvent(ASS_COMMENT)))


class ScriptTestBase(unittest.TestCase):
    def setUp(self):
        self.script_description, self.script_path = tempfile.mkstemp()

    def tearDown(self):
        os.remove(self.script_path)


class SrtScriptTestCase(ScriptTestBase):
    def test_write_to_file(self):
        events = [SrtEvent.from_string(SINGLE_LINE_SRT_EVENT), SrtEvent.from_string(MULTILINE_SRT_EVENT)]
        SrtScript(events).save_to_file(self.script_path)
        with open(self.script_path) as script:
            text = script.read()
        self.assertEqual(SINGLE_LINE_SRT_EVENT + "\n\n" + MULTILINE_SRT_EVENT, text)

    def test_read_from_file(self):
        os.write(self.script_description, """1
00:00:17,500 --> 00:00:18,870
Yeah, really!

2
00:00:17,500 --> 00:00:18,870


3
00:00:17,500 --> 00:00:18,870
House number
35

4
00:00:21,250 --> 00:00:22,750
Serves you right.""")
        parsed = SrtScript.from_file(self.script_path).events
        self.assertEqual(17.5, parsed[0].start)
        self.assertEqual(18.87, parsed[0].end)
        self.assertEqual("Yeah, really!", parsed[0].text)
        self.assertEqual(17.5, parsed[1].start)
        self.assertEqual(18.87, parsed[1].end)
        self.assertEqual("", parsed[1].text)
        self.assertEqual(17.5, parsed[2].start)
        self.assertEqual(18.87, parsed[2].end)
        self.assertEqual("House number\n35", parsed[2].text)
        self.assertEqual(21.25, parsed[3].start)
        self.assertEqual(22.75, parsed[3].end)
        self.assertEqual("Serves you right.", parsed[3].text)


class AssScriptTestCase(ScriptTestBase):
    def test_write_to_file(self):
        styles = ["Style: Default,Open Sans Semibold,36,&H00FFFFFF,&H000000FF,&H00020713,&H00000000,-1,0,0,0,100,100,0,0,1,1.7,0,2,0,0,28,1"]
        events = [AssEvent(ASS_EVENT), AssEvent(ASS_EVENT)]
        AssScript([], styles, events, None).save_to_file(self.script_path)

        with codecs.open(self.script_path, encoding='utf-8-sig') as script:
            text = script.read()

        self.assertEqual("""[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Open Sans Semibold,36,&H00FFFFFF,&H000000FF,&H00020713,&H00000000,-1,0,0,0,100,100,0,0,1,1.7,0,2,0,0,28,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{0}
{0}""".format(ASS_EVENT), text)

    def test_read_from_file(self):
        text = """[Script Info]
; Script generated by Aegisub 3.1.1
Title: script title

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Open Sans Semibold,36,&H00FFFFFF,&H000000FF,&H00020713,&H00000000,-1,0,0,0,100,100,0,0,1,1.7,0,2,0,0,28,1
Style: Signs,Gentium Basic,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.42,0:00:03.36,Default,,0000,0000,0000,,As you already know,
Dialogue: 0,0:00:03.36,0:00:05.93,Default,,0000,0000,0000,,I'm concerned about the hair on my nipples."""

        os.write(self.script_description, text)
        script = AssScript.from_file(self.script_path)
        self.assertEqual(["; Script generated by Aegisub 3.1.1", "Title: script title"], script.script_info)
        self.assertEqual(["Style: Default,Open Sans Semibold,36,&H00FFFFFF,&H000000FF,&H00020713,&H00000000,-1,0,0,0,100,100,0,0,1,1.7,0,2,0,0,28,1",
                          "Style: Signs,Gentium Basic,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,10,10,10,1"],
                         script.styles)
        self.assertEqual([1, 2], [x.source_index for x in script.events])
        self.assertEqual("Dialogue: 0,0:00:01.42,0:00:03.36,Default,,0000,0000,0000,,As you already know,", str(script.events[0]))
        self.assertEqual("Dialogue: 0,0:00:03.36,0:00:05.93,Default,,0000,0000,0000,,I'm concerned about the hair on my nipples.", str(script.events[1]))

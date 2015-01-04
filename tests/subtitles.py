import unittest
from subs import AssEvent, AssScript, SrtEvent, SrtScript


class SrtEventTestCase(unittest.TestCase):
    single_line_text = """228
00:14:21,960 --> 00:14:22,960
HOW DID IT END UP LIKE THIS?"""

    multi_line_text = """203
00:13:12,140 --> 00:13:14,100
APPEARANCE!
Appearrance (teisai)!
No wait, you're the worst (saitei)!"""

    def test_simple_parsing(self):
        event = SrtEvent(self.single_line_text)
        self.assertEquals(228, event.idx)
        self.assertEquals(14*60+21.960, event.start)
        self.assertEquals(14*60+22.960, event.end)
        self.assertEquals("HOW DID IT END UP LIKE THIS?", event.text)

    def test_multi_line_event_parsing(self):
        event = SrtEvent(self.multi_line_text)
        self.assertEquals(203, event.idx)
        self.assertEquals(13*60+12.140, event.start)
        self.assertEquals(13*60+14.100, event.end)
        self.assertEquals("APPEARANCE!\nAppearrance (teisai)!\nNo wait, you're the worst (saitei)!", event.text)

    def test_parsing_and_printing(self):
        self.assertEquals(self.single_line_text, unicode(SrtEvent(self.single_line_text)))
        self.assertEquals(self.multi_line_text, unicode(SrtEvent(self.multi_line_text)))


class AssEventTestCase(unittest.TestCase):
    dialogue_line = r"Dialogue: 0,0:18:50.98,0:18:55.28,Default,,0,0,0,,Are you trying to (ouch) crush it (ouch)\N like a (ouch) vise (ouch, ouch)?"
    comment_line = r"Comment: 0,0:18:09.15,0:18:10.36,Default,,0,0,0,,I DON'T GET IT TOO WELL."

    def test_simple_parsing(self):
        event = AssEvent(self.dialogue_line)
        self.assertFalse(event.is_comment)
        self.assertEquals("Dialogue", event.kind)
        self.assertEquals(18*60+50.98, event.start)
        self.assertEquals(18*60+55.28, event.end)
        self.assertEquals("0", event.layer)
        self.assertEquals("Default", event.style)
        self.assertEquals("", event.name)
        self.assertEquals("0", event.margin_left)
        self.assertEquals("0", event.margin_right)
        self.assertEquals("0", event.margin_vertical)
        self.assertEquals("", event.effect)
        self.assertEquals("Are you trying to (ouch) crush it (ouch)\N like a (ouch) vise (ouch, ouch)?", event.text)

    def test_comment_parsing(self):
        event = AssEvent(self.comment_line)
        self.assertTrue(event.is_comment)
        self.assertEquals("Comment", event.kind)

    def test_parsing_and_printing(self):
        self.assertEquals(self.dialogue_line, unicode(AssEvent(self.dialogue_line)))
        self.assertEquals(self.comment_line, unicode(AssEvent(self.comment_line)))

import logging
from subs import AssScript, SrtScript
from wav import WavStream
import sys
from collections import namedtuple
from itertools import takewhile
import numpy as np
import argparse
import chapters
import os.path
from time import time

allowed_error = 0.01


def abs_diff(a, b):
    return max(a, b) - min(a, b)


def groups_from_chapters(events, times):
    times = list(times) # copy
    times.append(36000000000) # very large event at the end
    logging.debug('Chapter start points: {0}'.format(times))
    groups = [[]]
    current_chapter = 0

    for event in events:
        if event.start.total_seconds > times[current_chapter+1]:
            groups.append([])
            current_chapter += 1

        groups[-1].append(event)

    if not groups[-1]:
        del groups[-1]

    for g in groups:
        if abs_diff(g[0].shift, g[-1].shift) > allowed_error:
            logging.warn(u'Shift is very different at the edges of a chapter group, most likely chapters are wrong. '
                         'First line in the group: {0}'.format(unicode(g[0])))
        logging.debug('Group (start={0}, end={1}, lines={2}), shift: {3}'.format(g[0].start, g[-1].end, len(g), g[0].shift))
    return groups


def detect_groups(events):
    Group = namedtuple('Group', ['start', 'end'])

    start_index = 0
    last_shift = events[0].shift
    groups = []
    for idx, event in enumerate(events):
        if abs_diff(event.shift, last_shift) > allowed_error:
            groups.append(Group(start_index, idx - 1))
            last_shift = event.shift
            start_index = idx

    # last group
    if start_index < len(events) - 2:
        groups.append(Group(start_index, len(events) - 2))

    # todo: merge very short groups
    for g in groups:
        logging.debug('Group (start={0}, end={1}, lines={2}), shift: {3}'.format(
            events[g.start].start, events[g.end].end, g.end+1-g.start, events[g.start].shift))

    return [events[g.start:g.end + 1] for g in groups]


def calculate_shifts(src_stream, dst_stream, events, window, fast_skip):
    small_window = 2
    last_shift = 0
    for idx, event in enumerate(events):
        if event.end == event.start:
            logging.debug('{0}: skipped because zero duration'.format(event.start))
            if idx == 0:
                event.mark_broken()
            else:
                event.copy_shift_from(events[idx - 1])
            continue

        if fast_skip:
            shift_set = False
            for processed in reversed(events[:idx]):
                if processed.start == event.start and processed.end == event.end:
                    # logging.debug('{0}: skipped because identical to already processed (typesetting?)'.format(event.start))
                    event.copy_shift_from(processed)
                    shift_set = True
            if shift_set:
                continue

        if event.start.total_seconds > src_stream.duration_seconds:
            logging.info('Event time outside of audio range, ignoring: %s' % unicode(event))
            event.mark_broken()
            continue

        tv_audio = src_stream.get_substream(event.start.total_seconds, event.end.total_seconds)

        original_time = event.start.total_seconds
        start_point = original_time + last_shift

        # searching with smaller window
        diff, new_time = dst_stream.find_substream(tv_audio,
                                                   start_time=start_point - small_window,
                                                   end_time=start_point + small_window)

        # checking if times are close enough to last shift - no point in re-searching with full window if it's in the same group
        if abs_diff(new_time - original_time, last_shift) > allowed_error:
            diff, new_time = dst_stream.find_substream(tv_audio,
                                                       start_time=start_point - window,
                                                       end_time=start_point + window)

        last_shift = time_offset = new_time - original_time
        event.set_shift(time_offset, diff)
        logging.debug('{0}: {1}, diff: {2}'.format(event.start, time_offset, diff))


def clip_obviously_wrong(events):
    for idx, event in enumerate(events):
        if event.diff < 0.5:  # somewhat random
            continue
        next_sane = next(x for x in events[idx + 1:] if x.diff < 0.5)

        # select the one with closest shift
        prev_sane = events[idx - 1]  # first is never broken because it's fixed in borders routine
        if abs_diff(prev_sane.shift, event.shift) < abs_diff(next_sane.shift, event.shift):
            event.copy_shift_from(prev_sane)
        else:
            event.copy_shift_from(next_sane)


def fix_near_borders(events):
    def fix_border(event_list):
        broken = list(takewhile(lambda x: x.diff > 0.5, event_list))
        if broken:
            sane = event_list[len(broken)]
            for x in broken:
                x.copy_shift_from(sane)

    fix_border(events)
    fix_border(list(reversed(events)))


def average_shifts(events):
    shifts = [x.shift for x in events]
    weights = [1 - x.diff for x in events]
    avg, weights_sum = np.average(shifts, weights=weights, returned=True)
    new_diff = 1 - weights_sum / len(events)
    logging.debug('Average weight set to {0}'.format(avg))
    for e in events:
        e.set_shift(avg, new_diff)


def apply_shifts(events):
    for e in events:
        e.apply_shift()


def get_extension(path):
    return (os.path.splitext(path)[1]).lower()

def run(args):
    format = "%(levelname)s: %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=format)

    src_ext = get_extension(args.input_script)
    dst_ext = get_extension(args.output_script)
    if src_ext != dst_ext:
        logging.critical("Source and destination file types don't match")
        sys.exit(2)

    if src_ext == '.ass':
        script = AssScript(args.input_script)
    elif src_ext == '.srt':
        script = SrtScript(args.input_script)
    else:
        logging.critical('Invalid file type')
        sys.exit(2)

    script.sort_by_time()

    src_stream = WavStream(args.src_audio, sample_rate=args.sample_rate, sample_type=args.sample_type)
    dst_stream = WavStream(args.dst_audio, sample_rate=args.sample_rate, sample_type=args.sample_type)

    calculate_shifts(src_stream, dst_stream, script.events, window=args.window, fast_skip=args.fast_skip)

    script.sort_broken()  # avoid processing broken lines with zero shifts
    events = [x for x in script.events if not x.broken]

    fix_near_borders(events)
    clip_obviously_wrong(events)

    if args.grouping:
        if args.chapters_file:
            if get_extension(args.chapters_file) == '.xml':
                times = chapters.get_xml_start_times(args.chapters_file)
            else:
                times = chapters.get_ogm_start_times(args.chapters_file)
            groups = groups_from_chapters(events, times)
        else:
            groups = detect_groups(events)

        for g in groups:
            average_shifts(g)
            apply_shifts(g)
    else:
        apply_shifts(events)

    script.save_to_file(args.output_script)


def create_arg_parser():
    parser = argparse.ArgumentParser(description='Sushi - Automatic Subtitle Shifter')

    parser.add_argument('--window', default=10, type=int, dest='window',
                        help='Search window size')
    parser.add_argument('--no-grouping', action='store_false', dest='grouping',
                        help='Split events into groups before shifting')

    # optimizations
    parser.add_argument('--no-fast-skip', action='store_false', dest='fast_skip',
                        help="Don't skip lines with identical timing")

    parser.add_argument('--sample-rate', default=12000, type=int, dest='sample_rate',
                        help='Downsampled audio sample rate')
    parser.add_argument('--sample-type', default='uint8', choices=['float32', 'uint8'], dest='sample_type',
                        help='Downsampled audio representation type')

    # files
    parser.add_argument('--chapters', default=None, dest='chapters_file', metavar='file',
                        help='Source XML or OGM chapters')
    parser.add_argument('--src-audio', required=True, dest="src_audio", metavar='file',
                        help='Source audio WAV')
    parser.add_argument('--dst-audio', required=True, dest="dst_audio", metavar='file',
                        help='Destination audio WAV')
    parser.add_argument('-o', '--output', required=True, dest='output_script', metavar='file',
                        help='Output script')
    parser.add_argument('input_script',
                        help='Input script')

    return parser


if __name__ == '__main__':
    args = create_arg_parser().parse_args(sys.argv[1:])
    start_time = time()
    run(args)
    logging.debug('Done in {0}s'.format(time() - start_time))
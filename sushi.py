import logging
from common import SushiError, get_extension
from demux import FFmpeg, get_media_info, read_timecodes, CfrTimecodes
from keyframes import parse_keyframes
from subs import AssScript, SrtScript
from wav import WavStream
import sys
from collections import namedtuple
from itertools import takewhile
import numpy as np
import argparse
import chapters
import os
from time import time
import bisect

ALLOWED_ERROR = 0.01
MAX_KEYFRAME_DISTANCE_FRAMES = 3


def abs_diff(a, b):
    return max(a, b) - min(a, b)


def detect_groups(events):
    Group = namedtuple('Group', ['start', 'end'])

    start_index = 0
    last_shift = events[0].shift
    groups = []
    for idx, event in enumerate(events):
        if abs_diff(event.shift, last_shift) > ALLOWED_ERROR:
            groups.append(Group(start_index, idx - 1))
            last_shift = event.shift
            start_index = idx

    # last group
    if start_index < len(events) - 2:
        groups.append(Group(start_index, len(events) - 2))

    # todo: merge very short groups
    return [events[g.start:g.end + 1] for g in groups]


def groups_from_chapters(events, times):
    times = list(times)  # copy
    times.append(36000000000)  # very large event at the end
    logging.debug('Chapter start points: {0}'.format(times))
    groups = [[]]
    current_chapter = 0

    for event in events:
        if event.start.total_seconds > times[current_chapter + 1]:
            groups.append([])
            current_chapter += 1

        groups[-1].append(event)

    if not groups[-1]:
        del groups[-1]

    broken_groups = [g for g in groups if abs_diff(g[0].shift, g[-1].shift) > ALLOWED_ERROR]
    correct_groups = [g for g in groups if g not in broken_groups]

    if broken_groups:
        for g in broken_groups:
            logging.warn(u'Shift is very different at the edges of a chapter group, most likely chapters are wrong. Switched to automatic grouping.\n'
                         'First line in the group: {0}'.format(unicode(g[0])))
            correct_groups.extend(detect_groups(g))
        correct_groups = sorted(correct_groups, key=lambda g: g[0].start.total_seconds)

        i = 0
        while i < len(correct_groups)-1:
            if abs_diff(correct_groups[i][-1].shift, correct_groups[i+1][0].shift) < ALLOWED_ERROR:
                correct_groups[i].extend(correct_groups[i+1])
                del correct_groups[i+1]
            else:
                i += 1

    return correct_groups


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
        diff = new_time = None
        if small_window < window:
            diff, new_time = dst_stream.find_substream(tv_audio,
                                                   start_time=start_point - small_window,
                                                   end_time=start_point + small_window)

        # checking if times are close enough to last shift - no point in re-searching with full window if it's in the same group
        if not new_time or abs_diff(new_time - original_time, last_shift) > ALLOWED_ERROR:
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


def find_keyframes_nearby(events, keyframes):
    def find_closest_kf(timestamp):
        idx = bisect.bisect_left(keyframes, timestamp)
        if idx == 0:
            return keyframes[0]
        if idx == len(keyframes):
            return keyframes[-1]
        before = keyframes[idx - 1]
        after = keyframes[idx]
        return after if after - timestamp < timestamp - before else before

    for event in events:
        before = find_closest_kf(event.start.total_seconds + event.shift)
        after = find_closest_kf(event.end.total_seconds + event.shift)
        event.set_keyframes(before, after)

def snap_to_keyframes(events, timecodes):
    distances = []
    frame_sizes = []
    for event in events:
        frame_sizes.append(timecodes.get_frame_size(event.start.total_seconds))
        for d in event.get_keyframes_distances():
            if d is not None and abs(d) < (MAX_KEYFRAME_DISTANCE_FRAMES * frame_sizes[-1]):
                distances.append(d)

    mean_fs = np.mean(frame_sizes)
    if not distances:
        logging.info('No lines close enough to keyframes. Mean frame size: {0}'.format(mean_fs))
        return
    mean = np.mean(distances)
    logging.debug('Mean distance to keyframes: {0}. Mean frame size: {1}'.format(mean, mean_fs))

    max_snap_distance = (3.0 / 4.0) * mean_fs
    if abs(mean) < max_snap_distance:
        logging.info('Looks close enough to keyframes, snapping')
        for event in events:
            event.adjust_shift(mean)


def average_shifts(events):
    shifts = [x.shift for x in events]
    weights = [1 - x.diff for x in events]
    avg, weights_sum = np.average(shifts, weights=weights, returned=True)
    new_diff = 1 - weights_sum / len(events)
    logging.debug('Average shift set to {0}'.format(avg))
    for e in events:
        e.set_shift(avg, new_diff)


def apply_shifts(events):
    for e in events:
        e.apply_shift()


def is_wav(path):
    return get_extension(path) == '.wav'


def check_file_exists(path, file_title):
    if path and not os.path.exists(path):
        raise SushiError("{0} file doesn't exist".format(file_title))


def select_stream(streams, chosen_idx, path, stream_type):
    format_streams = lambda streams: '\n'.join(
        '{0}{1}: {2}'.format(s.id, ' (%s)' % s.title if s.title else '', s.info) for s in streams)

    if not streams:
        raise SushiError('No {0} streams found in {1}'.format(stream_type.lower(), path))
    if chosen_idx is None:
        if len(streams) > 1:
            raise SushiError('More than one {0} stream found in {1}.\n'
                             'You need to specify the exact one to demux. Here are all candidate streams:\n'
                             '{2}'.format(stream_type.lower(), path, format_streams(streams)))
        return streams[0]
    try:
        return next(x for x in streams if x.id == chosen_idx)
    except StopIteration:
        raise SushiError("{0} stream with index {1} doesn't exist in {2}.\n"
                         'Here are all that do:\n'
                         '{3}'.format(stream_type, chosen_idx, path, format_streams(streams)))

def run(args):
    format = "%(levelname)s: %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=format)
    ignore_chapters = args.chapters_file is not None and args.chapters_file.lower() == 'none'

    # first part should do all possible validation and should NOT take significant amount of time
    check_file_exists(args.source, 'Source')
    check_file_exists(args.destination, 'Destination')
    check_file_exists(args.timecodes_file, 'Timecodes')
    check_file_exists(args.keyframes_file, 'Keyframes')
    check_file_exists(args.script_file, 'Script')

    if not ignore_chapters:
        check_file_exists(args.chapters_file, 'Chapters')

    if args.timecodes_file and args.dst_fps:
        raise SushiError('Both fps and timecodes file cannot be specified at the same time')

    if is_wav(args.source) and not args.script_file:
        raise SushiError("Script file isn't specified")

    chapter_times = []
    delete_dst_audio = delete_src_audio = delete_src_script = False

    if not is_wav(args.source):
        mi = get_media_info(args.source)
        src_audio_stream = select_stream(mi.audio, args.src_audio_idx, args.source, 'Audio').id
        chapter_times = mi.chapters
        if not args.script_file:
            scr = select_stream(mi.subtitles, args.src_script_idx, args.source, 'Subtitles')
            src_script_type = scr.type
            src_script_stream = scr.id

    if args.script_file:
        src_script_type = get_extension(args.script_file)

    if src_script_type not in ('.ass', '.src'):
        raise SushiError('Unknown script type')

    if not is_wav(args.destination):
        mi = get_media_info(args.destination)
        dst_audio_stream = select_stream(mi.audio, args.dst_audio_idx, args.destination, 'Audio').id

    if args.output_script and get_extension(args.output_script) != src_script_type:
        raise SushiError("Source and destination script file types don't match ({0} vs {1})"
                         .format(src_script_type, get_extension(args.output_script)))

    if args.keyframes_file:
        if args.timecodes_file:
            timecodes = read_timecodes(args.timecodes_file)
        elif args.dst_fps:
            timecodes = CfrTimecodes(args.dst_fps)
        else:
            raise SushiError('Fps or timecodes file must be provided if keyframes are used')

        kfs = parse_keyframes(args.keyframes_file)
        if not kfs:
            raise SushiError('No keyframes found in the provided keyframes file')
        kfs = [timecodes.get_frame_time(f) for f in kfs]
    else:
        kfs = None

    # after this point nothing should fail so it's safe to start demuxing and other slow operations

    if not is_wav(args.source):
        src_audio_path = args.source + '.sushi.wav'
        ffargs = {'audio_stream': src_audio_stream, 'audio_path': src_audio_path, 'audio_rate': args.sample_rate}
        if not args.script_file:
            ffargs['script_stream'] = src_script_stream
            ffargs['script_path'] = src_script_path = args.source + '.sushi' + src_script_type
            delete_src_script = True
        else:
            src_script_path = args.script_file
        FFmpeg.demux_file(args.source, **ffargs)
        delete_src_audio = True
    else:
        src_audio_path = args.source
        src_script_path = args.script_file

    if not is_wav(args.destination):
        dst_audio_path = args.destination + '.sushi.wav'
        FFmpeg.demux_file(args.destination,
                          audio_path=dst_audio_path,
                          audio_stream=dst_audio_stream,
                          audio_rate=args.sample_rate)
        delete_dst_audio = True
    else:
        dst_audio_path = args.destination

    if args.grouping and not ignore_chapters and args.chapters_file:
        if get_extension(args.chapters_file) == '.xml':
            chapter_times = chapters.get_xml_start_times(args.chapters_file)
        else:
            chapter_times = chapters.get_ogm_start_times(args.chapters_file)

    script = AssScript(src_script_path) if src_script_type == '.ass' else SrtScript(src_script_path)
    script.sort_by_time()

    src_stream = WavStream(src_audio_path, sample_rate=args.sample_rate, sample_type=args.sample_type)
    dst_stream = WavStream(dst_audio_path, sample_rate=args.sample_rate, sample_type=args.sample_type)

    calculate_shifts(src_stream, dst_stream, script.events, window=args.window, fast_skip=args.fast_skip)

    script.sort_broken()  # avoid processing broken lines with zero shifts
    events = [x for x in script.events if not x.broken]

    fix_near_borders(events)
    clip_obviously_wrong(events)

    if args.grouping:
        if not ignore_chapters and chapter_times:
            groups = groups_from_chapters(events, chapter_times)
        else:
            groups = detect_groups(events)

        for g in groups:
            logging.debug('Group (start={0}, end={1}, lines={2}), shift: {3}'.format(g[0].start, g[-1].end, len(g), g[0].shift))
            average_shifts(g)
            if kfs:
                find_keyframes_nearby(g, kfs)
                snap_to_keyframes(g, timecodes)
    elif kfs:
        find_keyframes_nearby(events, kfs)
        snap_to_keyframes(events, timecodes)

    apply_shifts(events)

    if not args.output_script:
        args.output_script = args.destination + '.sushi' + src_script_type
    script.save_to_file(args.output_script)

    #cleanup
    if args.cleanup:
        if delete_dst_audio:
            os.remove(dst_audio_path)
        if delete_src_audio:
            os.remove(src_audio_path)
        if delete_src_script:
            os.remove(src_script_path)


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


    parser.add_argument('--src-audio', default=None, type=int, dest='src_audio_idx',
                        help='Audio stream index of the source video')
    parser.add_argument('--src-script', default=None, type=int, dest='src_script_idx',
                        help='Script stream index of the source video')
    parser.add_argument('--dst-audio', default=None, type=int, dest='dst_audio_idx',
                        help='Audio stream index of the destination video')
    # files
    parser.add_argument('--no-cleanup', action='store_false', dest='cleanup',
                        help="Don't delete demuxed streams")
    parser.add_argument('--chapters', default=None, dest='chapters_file', metavar='file',
                        help="XML or OGM chapters to use instead of any found in the source. 'none' to disable.")
    parser.add_argument('--script', default=None, dest='script_file', metavar='file',
                        help='Subtitle file path to use instead of any found in the source')
    parser.add_argument('--keyframes', default=None, dest='keyframes_file', metavar='file',
                        help='Keyframes file path to use.')
    parser.add_argument('--fps', default=None, type=float, dest='dst_fps', metavar='file',
                        help='Fps of destination video. Must be provided if keyframes are used.')
    parser.add_argument('--timecodes', default=None, dest='timecodes_file', metavar='file',
                        help='Timecodes file to use instead of making one from the source (when possible)')

    parser.add_argument('--src', required=True, dest="source", metavar='file',
                        help='Source audio/video')
    parser.add_argument('--dst', required=True, dest="destination", metavar='file',
                        help='Destination audio/video')
    parser.add_argument('-o', '--output', default=None, dest='output_script', metavar='file',
                        help='Output script')

    return parser


def parse_args_and_run(cmd_keys):
    args = create_arg_parser().parse_args(cmd_keys)
    start_time = time()
    run(args)
    logging.debug('Done in {0}s'.format(time() - start_time))


if __name__ == '__main__':
    try:
        parse_args_and_run(sys.argv[1:])
    except SushiError as e:
        logging.critical(e.message)
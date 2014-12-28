#!/usr/bin/env python
import logging
from common import SushiError, get_extension, format_time
from demux import Timecodes, Demuxer
from keyframes import parse_keyframes
from subs import AssScript, SrtScript
from wav import WavStream
import sys
from itertools import takewhile
import numpy as np
import argparse
import chapters
import os
from time import time
import bisect

try:
    import matplotlib.pyplot as plt
    plot_enabled = True
except:
    plot_enabled = False

ALLOWED_ERROR = 0.01
MAX_GROUP_STD = 0.025


def abs_diff(a, b):
    return abs(a - b)


def write_shift_avs(output_path, groups, src_audio, dst_audio):
    from collections import namedtuple

    Group = namedtuple('ShiftGroup', ['start', 'shift'])

    def format_trim(start, end, shift):
        return 'tv.trim({0},{1}).DelayAudio({2})'.format(start, end, shift)

    duration = int(groups[-1][-1].end * 24000.0 / 1001.0) + 100
    text = 'bd = Blackness({0}, 1920, 1080, "YV24").AudioDub(FFAudioSource("{1}")).WaveForm(zoom=1,height=1080).grayscale()\n' \
           'bd = bd.mt_merge(blackness({0}, 1920, 1080, color=$00800000).converttoyv24(), bd,luma=true)\n\n'.format(
        duration, os.path.abspath(dst_audio))

    text += 'tv = Blackness({0}, 1920, 1080, "YV24").AudioDub(FFAudioSource("{1}"))\n\n'.format(duration,
                                                                                                os.path.abspath(
                                                                                                    src_audio))
    text += 'tv = '
    groups = [Group(int(round(x[0].start * 24000.0 / 1001.0)), x[0].shift) for x in groups]

    text += format_trim(0, groups[1].start - 1, groups[0].shift) + ' ++\\\n\t\t'

    for idx in xrange(1, len(groups) - 1):
        text += format_trim(groups[idx].start, groups[idx + 1].start - 1, groups[idx].shift) + ' ++\\\n\t\t'

    text += format_trim(groups[-1].start, 0, groups[-1].shift) + '\n'
    text += 'tv = tv.WaveForm(zoom=1,height=1080).grayscale()\n\n' \
            'mt_logic(tv, bd, "max", u=3,v=3)\n'.format(duration)
    with open(output_path, 'w') as file:
        file.write(text)


def interpolate_nones(data, points):
    data = list(data)
    data_idx = [point for point, value in zip(points, data) if value is not None]
    if not data_idx:
        return []
    zero_idx = [point for point, value in zip(points, data) if value is None]
    if not zero_idx:
        return data
    data_values = [value for value in data if value is not None]
    out = iter(np.interp(zero_idx, data_idx, data_values))

    for point, value in enumerate(data):
        if value is None:
            data[point] = next(out, None)

    return data

# todo: implement this as a running median
def running_median(values, window_size):
    if window_size % 2 != 1:
        raise SushiError('Median window size should be odd')
    half_window = window_size // 2
    medians = []
    items_count = len(values)
    for idx in xrange(items_count):
        radius = min(half_window, idx, items_count-idx-1)
        med = np.median(values[idx-radius:idx+radius+1])
        medians.append(med)
    return medians


def smooth_events(events, radius):
    if not radius:
        return
    window_size = radius*2+1
    shifts = [e.shift for e in events]
    smoothed = running_median(shifts, window_size)
    for event, new_shift in zip(events, smoothed):
        event.set_shift(new_shift, event.diff)


def detect_groups(events, min_group_size):
    last_shift = events[0].shift
    current_group = []
    groups = []
    for e in events:
        if abs_diff(e.shift, last_shift) > ALLOWED_ERROR:
            groups.append(current_group)
            current_group = [e]
            last_shift = e.shift
        else:
            current_group.append(e)
    groups.append(current_group)

    if not any(g for g in groups if len(g) >= min_group_size):
        return groups  # not a single large group to merge into

    large = []
    groups = iter(groups)
    a = next(groups, None)
    while a is not None:
        if len(a) >= min_group_size:
            large.append(a)
            a = next(groups, None)
        else:
            small = []
            while a and len(a) < min_group_size:
                small.extend(a)
                a = next(groups, None)

            if not large:
                a = small + a  # no large groups before, extend the next one
            elif not a:
                large[-1].extend(small)  # next group doesn't exist, extend the previous one
            elif abs_diff(a[0].shift, small[-1].shift) < abs_diff(large[-1][-1].shift, small[0].shift):
                a = small + a  # next group has closer diff then the next one
            else:
                large[-1].extend(small)

    return large


def groups_from_chapters(events, times):
    logging.debug(u'Chapter start points: {0}'.format([format_time(t) for t in times]))
    groups = [[]]
    chapter_times = iter(times[1:] + [36000000000])  # very large event at the end
    current_chapter = next(chapter_times)

    for event in events:
        if event.end > current_chapter:
            groups.append([])
            while event.end > current_chapter:
                current_chapter = next(chapter_times)

        groups[-1].append(event)

    return [g for g in groups if g]


def split_broken_groups(groups, min_auto_group_size):
    correct_groups = []
    broken_found = False
    for g in groups:
        std = np.std([e.shift for e in g])
        if std > MAX_GROUP_STD:
            logging.warn(u'Shift is not consistent between {0} and {1}, most likely chapters are wrong (std: {2}). '
                         u'Switching to automatic grouping.'.format(format_time(g[0].start), format_time(g[-1].end),
                                                                    std))
            correct_groups.extend(detect_groups(g, min_auto_group_size))
            broken_found = True
        else:
            correct_groups.append(g)

    if broken_found:
        correct_groups.sort(key=lambda g: g[0].start)

        i = 0
        while i < len(correct_groups) - 1:
            if abs_diff(correct_groups[i][-1].shift, correct_groups[i + 1][0].shift) < ALLOWED_ERROR \
                    and np.std([e.shift for e in correct_groups[i] + correct_groups[i + 1]]) < MAX_GROUP_STD:
                correct_groups[i].extend(correct_groups[i + 1])
                del correct_groups[i + 1]
            else:
                i += 1

    return correct_groups


def fix_near_borders(events):
    """
    We assume that all lines with diff greater than 5 * (median diff across all events) are broken
    """
    def fix_border(event_list, median_diff):
        last_ten_diff = np.median([x.diff for x in event_list[:10]], overwrite_input=True)
        diff_limit = min(last_ten_diff, median_diff)*5
        broken = []
        for event in event_list:
            if event.diff > diff_limit:
                broken.append(event)
            else:
                for x in broken:
                    x.link_event(event)
                return len(broken)
        return 0

    median_diff = np.median([x.diff for x in events], overwrite_input=True)

    fixed_count = fix_border(events, median_diff)
    if fixed_count:
        logging.debug('Fixing {0} events near start'.format(fixed_count))

    fixed_count = fix_border(list(reversed(events)), median_diff)
    if fixed_count:
        logging.debug('Fixing {0} events near end'.format(fixed_count))


def get_distance_to_closest_kf(timestamp, keyframes):
    idx = bisect.bisect_left(keyframes, timestamp)
    if idx == 0:
        kf = keyframes[0]
    elif idx == len(keyframes):
        kf = keyframes[-1]
    else:
        before = keyframes[idx - 1]
        after = keyframes[idx]
        kf = after if after - timestamp < timestamp - before else before
    return kf - timestamp


def find_keyframe_shift(group, src_keytimes, dst_keytimes, src_timecodes, dst_timecodes, max_kf_distance):
    def get_distance(src_distance, dst_distance, limit):
        if abs(dst_distance) > limit:
            return None
        shift = dst_distance - src_distance
        return shift if abs(shift) < limit else None

    src_start = get_distance_to_closest_kf(group[0].start, src_keytimes)
    src_end = get_distance_to_closest_kf(group[-1].end + src_timecodes.get_frame_size(group[-1].end), src_keytimes)

    dst_start = get_distance_to_closest_kf(group[0].shifted_start, dst_keytimes)
    dst_end = get_distance_to_closest_kf(group[-1].shifted_end + dst_timecodes.get_frame_size(group[-1].end), dst_keytimes)

    snapping_limit_start = src_timecodes.get_frame_size(group[0].start) * max_kf_distance
    snapping_limit_end = src_timecodes.get_frame_size(group[0].end) * max_kf_distance

    return (get_distance(src_start, dst_start, snapping_limit_start),
            get_distance(src_end, dst_end, snapping_limit_end))


def find_keyframes_distances(event, src_keytimes, dst_keytimes, timecodes, max_kf_distance):
    def find_keyframe_distance(src_time, dst_time):
        src = get_distance_to_closest_kf(src_time, src_keytimes)
        dst = get_distance_to_closest_kf(dst_time, dst_keytimes)
        snapping_limit = timecodes.get_frame_size(src_time) * max_kf_distance

        if abs(src) < snapping_limit and abs(dst) < snapping_limit and abs(src-dst) < snapping_limit:
            return dst - src
        return 0

    ds = find_keyframe_distance(event.start, event.shifted_start)
    de = find_keyframe_distance(event.end, event.shifted_end)
    return ds, de


def snap_groups_to_keyframes(events, chapter_times, max_ts_duration, max_ts_distance, src_keytimes, dst_keytimes,
                             src_timecodes, dst_timecodes, max_kf_distance, kf_mode):
    if not max_kf_distance:
        return

    groups = merge_short_lines_into_groups(events, chapter_times, max_ts_duration, max_ts_distance)

    if kf_mode == 'all' or kf_mode == 'shift':
        #  step 1: snap events without changing their duration. Useful for some slight audio imprecision correction
        shifts = []
        times = []
        for group in groups:
            shifts.extend(find_keyframe_shift(group, src_keytimes, dst_keytimes, src_timecodes, dst_timecodes, max_kf_distance))
            times.extend((group[0].shifted_start, group[-1].shifted_end))

        shifts = interpolate_nones(shifts, times)
        if shifts:
            mean_shift = np.mean(shifts)
            shifts = zip(*(iter(shifts), ) * 2)

            logging.debug('Group {0}-{1} corrected by {2}'.format(format_time(events[0].start), format_time(events[-1].end), mean_shift))
            for group, shift in zip(groups, shifts):
                if abs(shift[0]-shift[1]) > 0.001 and len(group) > 1:
                    actual_shift = min(shift[0], shift[1], key=lambda x: abs(x - mean_shift))
                    logging.warning("Typesetting group at {0} had different shift at start/end points ({1} and {2}). Shifting by {3}."
                                    .format(format_time(group[0].start), shift[0], shift[1], actual_shift))
                    for e in group:
                        e.adjust_shift(actual_shift)
                else:
                    for e in group:
                        e.adjust_additional_shifts(shift[0], shift[1])

    if kf_mode == 'all' or kf_mode == 'snap':
        # step 2: snap start/end times separately
        for group in groups:
            if len(group) > 1:
                pass  # we don't snap typesetting
            start_shift, end_shift = find_keyframes_distances(group[0], src_keytimes, dst_keytimes, src_timecodes, max_kf_distance)
            if abs(start_shift) > 0.01 or abs(end_shift) > 0.01:
                logging.debug('Snapping {0} to keyframes, start time by {1}, end: {2}'.format(format_time(group[0].start), start_shift, end_shift))
                group[0].adjust_additional_shifts(start_shift, end_shift)


def average_shifts(events):
    events = [e for e in events if not e.linked]
    shifts = [x.shift for x in events]
    weights = [1 - x.diff for x in events]
    avg = np.average(shifts, weights=weights)
    for e in events:
        e.set_shift(avg, e.diff)
    return avg


def merge_short_lines_into_groups(events, chapter_times, max_ts_duration, max_ts_distance):
    search_groups = []
    chapter_times = iter(chapter_times[1:] + [100000000])
    next_chapter = next(chapter_times)
    events = list(events)

    processed = set()
    for idx, event in enumerate(events):
        if idx in processed:
            continue

        while event.end > next_chapter:
            next_chapter = next(chapter_times)

        if event.duration > max_ts_duration:
            search_groups.append([event])
            processed.add(idx)
        else:
            group = [event]
            i = idx+1
            while i < len(events) and abs(events[i].start - group[-1].end) < max_ts_distance:
                if events[i].end < next_chapter and events[i].duration <= max_ts_duration:
                    processed.add(i)
                    group.append(events[i])
                i += 1

            search_groups.append(group)

    return search_groups


def calculate_shifts(src_stream, dst_stream, events, chapter_times, window, max_ts_duration,
                     max_ts_distance):
    small_window = 1.5
    last_shift = 0

    for idx, event in enumerate(events):
        if event.is_comment:
            try:
                event.link_event(events[idx+1])
            except IndexError:
                event.link_event(events[idx-1])
            continue
        if (event.start + event.duration / 2.0) > src_stream.duration_seconds:
            logging.info('Event time outside of audio range, ignoring: %s' % unicode(event))
            event.link_event(next(x for x in reversed(events[:idx]) if not x.linked))
            continue
        elif event.end == event.start:
            logging.debug('{0}: skipped because zero duration'.format(format_time(event.start)))
            try:
                event.link_event(events[idx + 1])
            except IndexError:
                event.link_event(events[idx - 1])
            continue

        # assuming scripts are sorted by start time so we don't search the entire collection
        same_start = lambda x: event.start == x.start
        processed = next((x for x in takewhile(same_start, reversed(events[:idx])) if not x.linked and x.end == event.end),None)
        if processed:
            event.link_event(processed)
            # logging.debug('{0}-{1}: skipped because identical to already processed (typesetting?)'
            # .format(format_time(event.start), format_time(event.end)))

    events = (e for e in events if not e.linked)

    search_groups = merge_short_lines_into_groups(events, chapter_times, max_ts_duration, max_ts_distance)

    passed_groups = []
    for idx, group in enumerate(search_groups):
        try:
            other = next(
                x for x in reversed(search_groups[:idx]) if x[0].start <= group[0].start and x[-1].end >= group[-1].end)
            for event in group:
                event.link_event(other[0])
        except StopIteration:
            passed_groups.append(group)

    for idx, search_group in enumerate(passed_groups):
        tv_audio = src_stream.get_substream(search_group[0].start, search_group[-1].end)

        original_time = search_group[0].start
        start_point = original_time + last_shift

        # make sure we don't crash because lines aren't present in the destination stream
        if start_point > dst_stream.duration_seconds:
            logging.info('Search start point is larger than dst stream duration, ignoring: %s' % unicode(search_group[0]))
            for group in reversed(passed_groups[:idx]):
                link_to = next((x for x in reversed(group) if not x.linked), None)
                if link_to:
                    for e in search_group:
                        e.link_event(link_to)
                    break
            continue

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

        for e in search_group:
            e.set_shift(time_offset, diff)
        logging.debug('{0}-{1}: shift: {2:0.12f}, diff: {3:0.12f}'
                      .format(format_time(search_group[0].start), format_time(search_group[-1].end), time_offset, diff))


def apply_shifts(events):
    for e in events:
        e.apply_shift()


def check_file_exists(path, file_title):
    if path and not os.path.exists(path):
        raise SushiError("{0} file doesn't exist".format(file_title))


def run(args):
    ignore_chapters = args.chapters_file is not None and args.chapters_file.lower() == 'none'
    write_plot = plot_enabled and args.plot_path
    if write_plot:
        plt.clf()
        plt.ylabel('Shift, seconds')
        plt.xlabel('Event index')

    # first part should do all possible validation and should NOT take significant amount of time
    check_file_exists(args.source, 'Source')
    check_file_exists(args.destination, 'Destination')
    check_file_exists(args.src_timecodes, 'Source timecodes')
    check_file_exists(args.dst_timecodes, 'Source timecodes')
    check_file_exists(args.script_file, 'Script')

    if not ignore_chapters:
        check_file_exists(args.chapters_file, 'Chapters')
    if args.src_keyframes not in ('auto', 'make'):
        check_file_exists(args.src_keyframes, 'Source keyframes')
    if args.dst_keyframes not in ('auto', 'make'):
        check_file_exists(args.dst_keyframes, 'Destination keyframes')

    if (args.src_timecodes and args.src_fps) or (args.dst_timecodes and args.dst_fps):
        raise SushiError('Both fps and timecodes file cannot be specified at the same time')

    src_demuxer = Demuxer(args.source)
    dst_demuxer = Demuxer(args.destination)

    if src_demuxer.is_wav and not args.script_file:
        raise SushiError("Script file isn't specified")

    if (args.src_keyframes and not args.dst_keyframes) or (args.dst_keyframes and not args.src_keyframes):
        raise SushiError('Either none or both of src and dst keyframes should be provided')

    # selecting source audio
    if src_demuxer.is_wav:
        src_audio_path = args.source
    else:
        src_audio_path = args.source + '.sushi.wav'
        src_demuxer.set_audio(stream_idx=args.src_audio_idx, output_path=src_audio_path, sample_rate=args.sample_rate)

    # selecting destination audio
    if dst_demuxer.is_wav:
        dst_audio_path = args.destination
    else:
        dst_audio_path = args.destination + '.sushi.wav'
        dst_demuxer.set_audio(stream_idx=args.dst_audio_idx, output_path=dst_audio_path, sample_rate=args.sample_rate)

    # selecting source subtitles
    if args.script_file:
        src_script_path = args.script_file
    else:
        stype = src_demuxer.get_subs_type(args.src_script_idx)
        src_script_path = args.source + '.sushi' + stype
        src_demuxer.set_script(stream_idx=args.src_script_idx, output_path=src_script_path)

    script_extension = get_extension(src_script_path)
    if script_extension not in ('.ass', '.srt'):
        raise SushiError('Unknown script type')

    # selection destination subtitles
    if args.output_script:
        dst_script_path = args.output_script
        dst_script_extension = get_extension(args.output_script)
        if dst_script_extension != script_extension:
            raise SushiError("Source and destination script file types don't match ({0} vs {1})"
                             .format(script_extension, dst_script_extension))
    else:
        dst_script_path = args.destination + '.sushi' + script_extension

    # selecting chapters
    if args.grouping and not ignore_chapters:
        if args.chapters_file:
            if get_extension(args.chapters_file) == '.xml':
                chapter_times = chapters.get_xml_start_times(args.chapters_file)
            else:
                chapter_times = chapters.get_ogm_start_times(args.chapters_file)
        elif not src_demuxer.is_wav:
            chapter_times = src_demuxer.chapters
        else:
            chapter_times = []
    else:
        chapter_times = []

    # selecting keyframes and timecodes
    if args.src_keyframes:
        def select_keyframes(file_arg, demuxer):
            auto_file = demuxer.path + '.sushi.keyframes.txt'
            if file_arg in ('auto', 'make'):
                if file_arg == 'make' or not os.path.exists(auto_file):
                    if not demuxer.has_video:
                        raise SushiError("Cannot make keyframes for {0} because it doesn't have any video!"
                                         .format(demuxer.path))
                    demuxer.set_keyframes(output_path=auto_file)
                return auto_file
            else:
                return file_arg

        def select_timecodes(external_file, fps_arg, demuxer):
            if external_file:
                return external_file
            elif fps_arg:
                return None
            elif demuxer.has_video:
                path = demuxer.path + '.sushi.timecodes.txt'
                demuxer.set_timecodes(output_path=path)
                return path
            else:
                raise SushiError('Fps, timecodes or video files must be provided if keyframes are used')

        src_keyframes_file = select_keyframes(args.src_keyframes, src_demuxer)
        dst_keyframes_file = select_keyframes(args.dst_keyframes, dst_demuxer)
        src_timecodes_file = select_timecodes(args.src_timecodes, args.src_fps, src_demuxer)
        dst_timecodes_file = select_timecodes(args.dst_timecodes, args.dst_fps, dst_demuxer)

    # after this point nothing should fail so it's safe to start slow operations
    # like running the actual demuxing
    src_demuxer.demux()
    dst_demuxer.demux()

    try:
        if args.src_keyframes:
            src_timecodes = Timecodes.cfr(args.src_fps) if args.src_fps else Timecodes.from_file(src_timecodes_file)
            src_keytimes = [src_timecodes.get_frame_time(f) for f in parse_keyframes(src_keyframes_file)]

            dst_timecodes = Timecodes.cfr(args.dst_fps) if args.dst_fps else Timecodes.from_file(dst_timecodes_file)
            dst_keytimes = [dst_timecodes.get_frame_time(f) for f in parse_keyframes(dst_keyframes_file)]

        script = AssScript(src_script_path) if script_extension == '.ass' else SrtScript(src_script_path)
        script.sort_by_time()

        src_stream = WavStream(src_audio_path, sample_rate=args.sample_rate, sample_type=args.sample_type)
        dst_stream = WavStream(dst_audio_path, sample_rate=args.sample_rate, sample_type=args.sample_type)

        calculate_shifts(src_stream, dst_stream, script.events,
                         chapter_times=chapter_times,
                         window=args.window,
                         max_ts_duration=args.max_ts_duration,
                         max_ts_distance=args.max_ts_distance)

        events = script.events

        if write_plot:
            plt.plot([x.shift for x in events], label='From audio')

        if args.grouping:
            if not ignore_chapters and chapter_times:
                groups = groups_from_chapters(events, chapter_times)
                for g in groups:
                    fix_near_borders(g)
                    smooth_events([x for x in g if not x.linked], args.smooth_radius)
                groups = split_broken_groups(groups, args.min_group_size)
            else:
                fix_near_borders(events)
                smooth_events([x for x in events if not x.linked], args.smooth_radius)
                groups = detect_groups(events, args.min_group_size)

            if write_plot:
                plt.plot([x.shift for x in events], label='Borders fixed')

            for g in groups:
                start_shift = g[0].shift
                end_shift = g[-1].shift
                avg_shift = average_shifts(g)
                logging.info(u'Group (start: {0}, end: {1}, lines: {2}), '
                             u'shifts (start: {3}, end: {4}, average: {5})'
                             .format(format_time(g[0].start), format_time(g[-1].end), len(g), start_shift, end_shift,
                                     avg_shift))

            if args.src_keyframes:
                for e in (x for x in events if x.linked):
                    e.resolve_link()
                for g in groups:
                    snap_groups_to_keyframes(g, chapter_times, args.max_ts_duration, args.max_ts_distance, src_keytimes,
                                             dst_keytimes, src_timecodes, dst_timecodes, args.max_kf_distance, args.kf_mode)

            if args.write_avs:
                write_shift_avs(dst_script_path + '.avs', groups, src_audio_path, dst_audio_path)
        else:
            fix_near_borders(events)
            if write_plot:
                plt.plot([x.shift for x in events], label='Borders fixed')

        if not args.grouping and args.src_keyframes:
            for e in (x for x in events if x.linked):
                e.resolve_link()
            snap_groups_to_keyframes(events, chapter_times, args.max_ts_duration, args.max_ts_distance, src_keytimes,
                                     dst_keytimes, src_timecodes, dst_timecodes, args.max_kf_distance, args.kf_mode)


        apply_shifts(events)

        script.save_to_file(dst_script_path)

        if write_plot:
            plt.plot([x.shift + (x._start_shift + x._end_shift)/2.0 for x in events], label='After correction')
            plt.legend(fontsize=5, frameon=False, fancybox=False)
            plt.savefig(args.plot_path, dpi=300)

    finally:
        if args.cleanup:
            src_demuxer.cleanup()
            dst_demuxer.cleanup()


def create_arg_parser():
    parser = argparse.ArgumentParser(description='Sushi - Automatic Subtitle Shifter')

    parser.add_argument('--window', default=10, type=int, metavar='<size>', dest='window',
                        help='Search window size')
    parser.add_argument('--no-grouping', action='store_false', dest='grouping',
                        help='Split events into groups before shifting')
    parser.add_argument('--min-group-size', default=1, type=int, dest='min_group_size',
                        help='Minimum size of automatic group')
    parser.add_argument('--max-kf-distance', default=2, type=float, metavar='<frames>', dest='max_kf_distance',
                        help='Maximum keyframe snapping distance [0.75]')
    parser.add_argument('--kf-mode', default='all', choices=['shift', 'snap', 'all'], dest='kf_mode',
                        help='Keyframes-based shift correction/snapping mode')
    parser.add_argument('--smooth-radius', default=3, type=int, dest='smooth_radius',
                        help='Radius of smoothing median filter')

    # 10 frames at 23.976
    parser.add_argument('--max-ts-duration', default=1001.0 / 24000.0 * 10, type=float, metavar='<seconds>',
                        dest='max_ts_duration',
                        help='Maximum duration of a line to be considered typesetting')
    # 10 frames at 23.976
    parser.add_argument('--max-ts-distance', default=1001.0 / 24000.0 * 10, type=float, metavar='<seconds>',
                        dest='max_ts_distance',
                        help='Maximum distance between two adjacent typesetting lines to be merged')

    parser.add_argument('--test-write-avs', action='store_true', dest='write_avs',help=argparse.SUPPRESS)
    parser.add_argument('--test-shift-plot', default=None, dest='plot_path',help=argparse.SUPPRESS)

    # optimizations
    parser.add_argument('--sample-rate', default=12000, type=int, metavar='<rate>', dest='sample_rate',
                        help='Downsampled audio sample rate')
    parser.add_argument('--sample-type', default='uint8', choices=['float32', 'uint8'], dest='sample_type',
                        help='Downsampled audio representation type')

    parser.add_argument('--src-audio', default=None, type=int, metavar='<id>', dest='src_audio_idx',
                        help='Audio stream index of the source video')
    parser.add_argument('--src-script', default=None, type=int, metavar='<id>', dest='src_script_idx',
                        help='Script stream index of the source video')
    parser.add_argument('--dst-audio', default=None, type=int, metavar='<id>', dest='dst_audio_idx',
                        help='Audio stream index of the destination video')
    # files
    parser.add_argument('--no-cleanup', action='store_false', dest='cleanup',
                        help="Don't delete demuxed streams")
    parser.add_argument('--chapters', default=None, dest='chapters_file', metavar='<filename>',
                        help="XML or OGM chapters to use instead of any found in the source. 'none' to disable.")
    parser.add_argument('--script', default=None, dest='script_file', metavar='<filename>',
                        help='Subtitle file path to use instead of any found in the source')

    parser.add_argument('--dst-keyframes', default=None, dest='dst_keyframes', metavar='<filename>',
                        help='Destination keyframes file')
    parser.add_argument('--src-keyframes', default=None, dest='src_keyframes', metavar='<filename>',
                        help='Source keyframes file')
    parser.add_argument('--dst-fps', default=None, type=float, dest='dst_fps', metavar='<fps>',
                        help='Fps of the destination video. Must be provided if keyframes are used.')
    parser.add_argument('--src-fps', default=None, type=float, dest='src_fps', metavar='<fps>',
                        help='Fps of the source video. Must be provided if keyframes are used.')
    parser.add_argument('--dst-timecodes', default=None, dest='dst_timecodes', metavar='<filename>',
                        help='Timecodes file to use instead of making one from the destination (when possible)')
    parser.add_argument('--src-timecodes', default=None, dest='src_timecodes', metavar='<filename>',
                        help='Timecodes file to use instead of making one from the source (when possible)')

    parser.add_argument('--src', required=True, dest="source", metavar='<filename>',
                        help='Source audio/video')
    parser.add_argument('--dst', required=True, dest="destination", metavar='<filename>',
                        help='Destination audio/video')
    parser.add_argument('-o', '--output', default=None, dest='output_script', metavar='<filename>',
                        help='Output script')

    return parser


def parse_args_and_run(cmd_keys):
    args = create_arg_parser().parse_args(cmd_keys)
    start_time = time()
    run(args)
    logging.info('Done in {0}s'.format(time() - start_time))


if __name__ == '__main__':
    try:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
        parse_args_and_run(sys.argv[1:])
    except SushiError as e:
        logging.critical(e.message)
        sys.exit(2)

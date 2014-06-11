from json import load
import logging
import os
from subprocess import Popen
import sys
from common import format_time
from subs import AssScript
import re


def get_frame_number(timecode, fps):
    return int(timecode * fps)

tags_stripper = re.compile(r'{.*?}')

def strip_tags(text):
    return tags_stripper.sub(" ", text)


def count_overlaps(events):
    return sum(1 for idx in xrange(1, len(events)) if events[idx].start < events[idx-1].end)


def compare_scripts(ideal_path, test_path, fps, test_name):
    ideal = AssScript(ideal_path)
    test = AssScript(test_path)
    if len(test.events) != len(ideal.events):
        logging.critical("Script length didn't match: {0} in ideal vs {1} in test. Test {2}".format(len(ideal.events), len(test.events), test_name))
        return False
    ideal.sort_by_time()
    test.sort_by_time()
    failed = 0
    ft = format_time
    for idx, (i, t) in enumerate(zip(ideal.events, test.events)):
        i_start_frame = get_frame_number(i.start, fps)
        i_end_frame = get_frame_number(i.end, fps)

        t_start_frame = get_frame_number(t.start, fps)
        t_end_frame = get_frame_number(t.end, fps)

        if i_start_frame != t_start_frame and i_end_frame != t_end_frame:
            logging.debug(u'{0}: start and end time failed at "{1}". {2}-{3} vs {4}-{5}'.format(idx, strip_tags(i.text), ft(i.start), ft(i.end), ft(t.start), ft(t.end)))
            failed += 1
        elif i_end_frame != t_end_frame:
            logging.debug(u'{0}: end time failed at "{1}". {2} vs {3}'.format(idx, strip_tags(i.text), ft(i.end), ft(t.end)))
            failed += 1
        elif i_start_frame != t_start_frame:
            logging.debug(u'{0}: start time failed at "{1}". {2} vs {3}'.format(idx, strip_tags(i.text), ft(i.start), ft(t.start)))
            failed += 1
        else:
            logging.debug('{0}: good line'.format(idx))

    overlaps_before = count_overlaps(ideal.events)
    overlaps_after = count_overlaps(test.events)
    logging.info('Overlaps before: {0}, after: {1}, {2} new overlaps'.format(overlaps_before, overlaps_after, overlaps_after - overlaps_before))
    if failed:
        logging.info('Total lines: {0}, good: {1}, failed: {2}'.format(len(ideal.events), len(ideal.events)-failed, failed))
    else:
        logging.info('Done with no errors')


def run_test(base_path, test_name, params):
    def safe_add_key(args, key, name):
        try:
            args.extend((key, str(params[name])))
        except KeyError:
            pass

    folder = os.path.join(base_path, params['folder'])
    dst_path = os.path.join(folder, params['dst'])
    src_path = os.path.join(folder, params['src'])

    cmd = ['py', '-2', 'sushi.py', '--src', src_path, '--dst', dst_path]
    try:
        cmd.extend(('--src-keyframes', os.path.join(folder, params['src-keyframes'])))
        cmd.extend(('--dst-keyframes', os.path.join(folder, params['dst-keyframes'])))
    except KeyError:
        pass

    safe_add_key(cmd, '--src-script', 'src-script')
    safe_add_key(cmd, '--dst-script', 'dst-script')
    safe_add_key(cmd, '--max-kf-snapping', 'max-kf-snapping')

    output_path = dst_path + '.sushi.test.ass'
    cmd.extend(('-o', output_path))

    process = Popen(cmd)
    process.wait()
    if process.returncode != 0:
        logging.critical('Sushi failed on test "{0}"'.format(test_name))
        return False

    ideal_path = os.path.join(folder, params['ideal'])
    compare_scripts(ideal_path, output_path, params['fps'], test_name)


def run():
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    try:
        with open('tests.json') as file:
            json = load(file)
    except IOError as e:
        logging.critical(e)
        sys.exit(2)
    for test_name in json['tests']:
        params = json['tests'][test_name]
        try:
            enabled = not params['disabled']
        except KeyError:
            enabled = True
        if enabled:
            run_test(json['basepath'], test_name, params)
        else:
            logging.warn('Test "{0}" disabled'.format(test_name))



if __name__ == '__main__':
    run()
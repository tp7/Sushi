## Sushi ##
Automatic subtitle shifter for SRT and ASS based on audio streams.

### Disclaimer ###
This script is in beta so don't expect it to handle any complicated cases or malformed input, have nice error reporting or super advanced features.

### Purpose
Imagine you've got a subtitle file synced to one video file, but you want to use these subtitles with some other video you've got via totally legal ways. The common example is TV vs. BD releases, PAL vs. NTSC video and releases in different countries. In a lot of cases, subtitles won't match right away and you need to sync them.

The purpose of this script is to avoid all the hassle of manual syncing. It attempts to synchronize subtitles by finding similarities in audio streams. The script is very fast and can be used right when you want to watch something.

### How it works
You need to provide two audio files and a subtitle file (.ass or .srt) that matches one of those files. For every line in the subtitles, the script will extract corresponding audio from the source audio stream and will try to find the closest similar pattern in the destination audio stream. The shift found will be applied to the subtitles.

During loading, both audio streams will be downsampled and converted to internal representation suitable for OpenCV (12kHz, 8bit samples). You can control downsampling with `--sample-rate` and `--sample-type` arguments, however it's not recommended to touch these values unless you get some problems with the defaults or you have many small lines (e.g frame-by-frame typesetting usually works better with 24kHz).

Of course it won't search the whole stream for every line. Instead, a small window (2 seconds in every direction, 4 total) is searched first, centered at the `original time + shift of the last line` position. If the script cannot find a reasonably good match in this window, it increases the search area to a larger value (20 seconds total by default) and attempts to search again, but this time the closest found match will be considered correct. You can control the size of the larger search window using the `--window` argument.

Also, the script won't attempt to search for a line if a line with identical start and end times has been already processed. This is very useful for typesetting and can significantly improve performance.

Then, the script will try to split all lines into groups. It can either try to build these groups automatically (lines with similar shift are grouped), or get them from chapters (XML or OGM), provided with `--chapters` argument. This is done because it is very unlikely for every line to have its own shift (unless there's some frame rate problems). Shift values of all events in every group are used to calculate weighted average (where weight is the coefficient of similarity of audio streams, calculated before). Of course you can disable grouping with `--no-grouping` switch.

Finally, sushi applies calculated shift to every line and writes the output file.

### Usage
The minimal command line looks like this:
```
python sushi.py --src hdtv.wav --dst bluray.wav --script subs.ass
```
Output file name is optional - `"{destination_path}.sushi.{subtitles_format}"` is used by default.

### Demuxing
Sushi can use ffmpeg to automatically demux and decode streams from video files. Add ffmpeg to your PATH or put it into the same folder as sushi for it to work. 

You need three things for sushi to work:

1. Original audio stream
2. Destination audio stream
3. Subtitles file

By default sushi will try to extract all these things from the files you've provided. If there's more than one appropriate stream in the file (e.g. two audio stream in the provided mkv), sushi will print an error and ask you to add the appropriate `--src-audio x` argument, where `x` - index of the audio stream in the container. There are also `--dst-audio` and `--src-script` that work like this.
```
python sushi.py --src hdtv.mkv --dst bluray.mkv --src-audio 2
```
By default sushi will try to extract audio, subtitles and chapters from the source file and audio from the destination file. You can overwrite this behavior using `--script` and `--chapters` parameters. Whatever file you specify there will be used instead of anything found in the source. There is no setting to specify audio files.
```
python sushi.py --src hdtv.mkv --dst bluray.mkv --script external.srt
```
If there is some chapters in the provided file but for some reason you don't want to use any chapters at all, you can use write `--chapters none` to disable them. Automatic grouping will be used instead (unless disabled).

After the job is done, sushi will delete all demuxed streams. To avoid this, you can use the `--no-cleanup` switch.

### Requirements
For the time being, the script is provided as-is. I don't know what exact versions you need to run it, but here's my environment:

1. Windows, but it probably will run on most other operation systems
2. [Python 2.7.6][1] (won't run on 3.x)
3. [NumPy 1.8.1][2]
4. [OpenCV 2.4.9][3] (putting [this file][4] in the same folder as sushi should be enough)
5. [FFmpeg][5] (only if demuxing is used)
6. [MkvExtract][6] (optional for faster timecodes extraction when demuxing)


### Limitations
This script will never be able to property handle frame-by-frame typesetting. If underlying video stream changes (e.g. has different telecine pattern), you might get incorrect output.

This script cannot improve bad timing. If original lines are mistimed, they will be mistimed in the output file too.

In short, while this might be safe for immediate viewing, you probably shouldn't use it to blindly shift subtitles for permanent storing.


  [1]: https://www.python.org/download/releases/2.7.6/
  [2]: http://www.scipy.org/scipylib/download.html
  [3]: http://opencv.org/
  [4]: https://dl.dropboxusercontent.com/u/54253260/DoNotDelete/cv2.pyd
  [5]: http://www.ffmpeg.org/download.html
  [6]: http://www.bunkus.org/videotools/mkvtoolnix/downloads.html
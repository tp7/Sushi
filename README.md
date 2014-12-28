## Sushi ##
Automatic shifter for SRT and ASS subtitle based on audio streams.

### Purpose
Imagine you've got a subtitle file synced to one video file, but you want to use these subtitles with some other video you've got via totally legal means. The common example is TV vs. BD releases, PAL vs. NTSC video and releases in different countries. In a lot of cases, subtitles won't match right away and you need to sync them.

The purpose of this script is to avoid all the hassle of manual syncing. It attempts to synchronize subtitles by finding similarities in audio streams. The script is very fast and can be used right when you want to watch something.

### Downloads
The latest binary release can always be found in the [releases][1] section. You need the green button on the top entry.

### How it works
You need to provide two audio files and a subtitle file that matches one of those files. For every line of the subtitles, the script will extract corresponding audio from the source audio stream and will try to find the closest similar pattern in the destination audio stream, obtaining a shift value which is later applied to the subtitles.

Detailed explanation of Sushi workflow and description of command-line arguments can be found in the [wiki][2].

### Usage
The minimal command line looks like this:
```
python sushi.py --src hdtv.wav --dst bluray.wav --script subs.ass
```
Output file name is optional - `"{destination_path}.sushi.{subtitles_format}"` is used by default. See the [usage][3] page of the wiki for further examples.

Do note that WAV is not the only format Sushi can work with. It can process audio/video files directly and decode various audio formats, provided that ffmpeg is available. For additional info refer to the [Demuxing][4] part of the wiki.

### Requirements
Sushi should work on Windows, Linux and OS X. Please open an issue if it doesn't. To run it, you have to have the following installed:

1. [Python 2.7.x][5]
2. [NumPy][6] (1.8 or newer)
3. [OpenCV 2.4.9][7] (on Windows putting [this file][8] in the same folder as Sushi should be enough, assuming you use x86 Python)
4. [FFmpeg][9] (only if demuxing is used)
5. [MkvExtract][10] (optional for faster timecodes extraction when demuxing)
6. [SCXvid-standalone][11] (only if keyframes are made by Sushi)

The provided Windows binaries include Python, NumPy and OpenCV so you don't have to install them if you use the binary distribution. You still have to download other applications yourself if you want to use Sushi's demuxing capabilities.

### Limitations
This script will never be able to property handle frame-by-frame typesetting. If underlying video stream changes (e.g. has different telecine pattern), you might get incorrect output.

This script cannot improve bad timing. If original lines are mistimed, they will be mistimed in the output file too.

In short, while this might be safe for immediate viewing, you probably shouldn't use it to blindly shift subtitles for permanent storing.


  [1]: https://github.com/tp7/Sushi/releases
  [2]: https://github.com/tp7/Sushi/wiki
  [3]: https://github.com/tp7/Sushi/wiki/Examples
  [4]: https://github.com/tp7/Sushi/wiki/Demuxing
  [5]: https://www.python.org/download/releases/2.7.8/
  [6]: http://www.scipy.org/scipylib/download.html
  [7]: http://opencv.org/
  [8]: https://dl.dropboxusercontent.com/u/54253260/DoNotDelete/cv2.pyd
  [9]: http://www.ffmpeg.org/download.html
  [10]: http://www.bunkus.org/videotools/mkvtoolnix/downloads.html
  [11]: https://github.com/soyokaze/SCXvid-standalone/releases

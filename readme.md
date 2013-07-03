Scenic: Video Scene Detection and Analysis
==========================================

A windows tool for categorising video files by scene and tagging each scene by colour, motion and the existence of faces. Written in python using avisynth (for video reading), SCXvid for scene change detection, mvtools2 for motion detection, PIL (for image quantization) and OpenCV (for face detection).

Binaries
--------

Windows executables are available on the [github releases page](https://github.com/AbsoluteDestiny/scenic/releases).

Command Line Arguments
----------------------

    Usage:
      scenic.py
      scenic.py [<PATH>...]
      scenic.py [--skip | --overwrite] [options] [<PATH>...]
      scenic.py (-h | --help)
      scenic.py --version

    Options:
      --skip        Skip file if .html file exists.
      --overwrite   Always overwrite any existing output files.
      --frames=N    Number of frames to sample per scene. [default: 4]
      --minscene=N  Smallest allowed scene length in frames. [default: 10]
      --faces=N     Process 1 in N samples for face detection. [default: 1]
      --colours=N   Number of colours to detect per scene. [default: 6]
      --cpus=N      Number of logical processors to use. Uses all by default.
      --silent      Silent mode. Use --skip or --overwrite to surpress dialogs.
      --no-colours  Do not tag scenes by colour.
      --no-motion   Disable motion Detection.
      --no-face     Disable scene face recognition.
      --no-popups   Do not open generated html in the web browser.
      --no-xml      Do not generate the FCP .xml file.
      --version     Show version.
      -h --help     Show this screen.

Dependencies
------------

* PIL
* OpenCV
* numpy
* jinja2
* webcolours
* docopt
* [python-progressbar](https://code.google.com/p/python-progressbar/)
* [python-colormath](https://code.google.com/p/python-colormath/)

Required 3rd party files and Binaries
-------------------------------------

These should be copied to the /resources/ folder.

* [MediaInfo.dll](http://mediainfo.sourceforge.net/en)
* avisynth.dll (from [Avisynth version 2.5.8](http://sourceforge.net/projects/avisynth2/files/AviSynth%202.5/))
* devil.dll (as included with Avisynth 2.5)
* msvcp60.dll (for Avisynth if not available already)
* [ffms2.dll and ffindex.exe](https://code.google.com/p/ffmpegsource/)
* [SCXvid.dll](http://unanimated.xtreemhost.com/scxvid.htm)
* [mvtools2.dll](http://avisynth.org.ru/mvtools/mvtools2.html)
* [jquery](http://code.jquery.com/jquery-1.10.1.min.js)

Building with PyInstaller
-------------------------
I use the following command:

    python -O /path/to/pyinstaller-script.py --onefile --upx-dir=/path/to/upx/ scenic.spec

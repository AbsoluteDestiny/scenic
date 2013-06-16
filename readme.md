Scenic: Video Scene Detection and Analysis
==========================================

A windows tool for categorising video files by scene and tagging each scene by colour, motion and the existence of faces. Written in python using avisynth (for video reading), SCXvid for scene change detection, mvtools2 for motion detection, PIL (for image quantization) and OpenCV (for face detection).

Dependencies
------------

* PIL
* OpenCV
* numpy
* scipy
* jinja2
* webcolours
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
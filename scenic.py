"""Scenic: Scene colour and motion analysis for video files.
Pass in a file or a directory of files for analysis.

Usage:
  scenic.py [<PATH>] [--skip | --overwrite] [options]
  scenic.py (-h | --help)
  scenic.py --version

Options:
  --skip        Skip file if .html file exists.
  --overwrite   Always overwrite any existing output files.
  --silent      Silent mode. Use --skip or --overwrite to surpress dialogs.
  --no-popups   Do not open generated html in the web browser
  --no-xml      Do not generate the FCP .xml file
  --version     Show version.
  -h --help     Show this screen.

"""
import sys
import os

if getattr(sys, 'frozen', False):
    # we are running in a |PyInstaller| bundle
    basedir = sys._MEIPASS
    __doc__ = __doc__.replace(".py", ".exe")
else:
    # we are running in a normal Python environment
    basedir = os.path.dirname(__file__)

import ctypes
import ctypes.wintypes
import shutil
import webbrowser
from collections import defaultdict
from functools import wraps
from math import ceil
from subprocess import check_output

# GUI
import Tkinter
import tkMessageBox
import tkFileDialog

#3rd party tools
import numpy
import progressbar as pb
import face
from PIL import Image
from jinja2 import Template
from docopt import docopt

from avisynth.pyavs import AvsClip
from avisynth import avisynth
from color import get_colour_name, most_frequent_colours, kelly_colours
from xmlgen import make_xml


version_string = ""
frozen_version = os.path.join(basedir, "frozen_version.txt")
try:
    if getattr(sys, 'frozen', False):
        version_string = open(frozen_version, "r").read().strip()
    else:
        version_string = "%s" % check_output(['git', 'describe'])
except:
    pass

app_name = "Scenic %s: Movie Scene Detection and Analysis" % version_string
buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
ctypes.windll.shell32.SHGetFolderPathW(0, 5, 0, 0, buf)
my_documents = buf.value
ctypes.windll.kernel32.SetConsoleTitleA(app_name)

valid_filetypes = [
    ".avi",
    ".avs",
    ".dv",
    ".flv",
    ".m2v",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpg",
    ".ogv",
    ".vob",
    ".webm",
    ".wmv",
]


def takespread(sequence, num):
    """Yield an even spread of items from a sequence"""
    if len(sequence) < num:
        for x in sequence:
            yield sequence
    else:
        length = float(len(sequence))
        for i in range(num):
            yield sequence[int(ceil(i * length / num))]


def get_numpy(avs, frame):
        """Given a frame number, return a numpy array from the clip"""
        avs._GetFrame(frame)
        end = avs.bmih.biWidth * avs.Height * 4
        data = avs.pBits[:end]
        # Somewhat fudgy way of turning avisynth pointers to numpy img
        # Get pixel data into numpy array. It comes out bottom left to top right.
        arrnew = numpy.array(data, dtype=numpy.uint8)
        arrnew = numpy.flipud(arrnew)  # Reverse the data so it's ARGBARGB...
        arrnew = arrnew.reshape(-1, 4)  # Array of [[A, R, G, B], [A, R, G, B]...]
        arrnew = numpy.roll(arrnew, -1)  # Array of [[R, G, B, A]...]
        arrnew = arrnew.reshape(avs.Height, avs.bmih.biWidth, 4)
        arrnew = numpy.fliplr(arrnew)
        return arrnew


def is_ready(func):
    @wraps(func)
    def wrapper(instance, *args, **kwds):
        if instance.ready:
            return func(instance, *args, **kwds)
    return wrapper


class AvisynthHelper(object):
    """Avisynth helper class. Adds with support."""
    def __init__(self, script):
        super(AvisynthHelper, self).__init__()
        self.script = script
        self.env = avisynth.avs_create_script_environment(1)

    def __enter__(self):
        self.r = self.env.Invoke("eval", avisynth.AVS_Value(self.script), 0)
        self.clip = AvsClip(self.r.AsClip(self.env), env=self.env)
        return self.clip

    def __exit__(self, t, value, traceback):
        if not t:
            return True


class Analyser(object):
    """Main class for holding Scenic arguments and methods.
       Usage: a = Analyser("/path/to/video/file")
              a.run()
       """

    def __init__(self, vidpath, skip=False, overwrite=False):
        if not vidpath:
            raise Exception("Analyser must have a vid path.")
        self.vidpath = vidpath
        self.rpath = os.path.realpath(os.path.join(basedir, "resources"))
        self.vidfn = os.path.split(vidpath)[1]
        self.vidname = os.path.splitext(self.vidfn)[0]
        self.vidroot = os.path.split(vidpath)[0]
        self.picpath = os.path.join(self.vidroot, "Scenes_%s" % self.vidname)
        self.htmlpath = os.path.join(self.vidroot, "%s.html" % self.vidname)
        self.vid_info = {}
        self.source = self.open_video()

        print "Processing video %s" % (self.vidfn)

        self.scenes = []  # A list of (start, end) frames
        self.times = {}  # A dictionary of frame: time in seconds
        self.vectors = {}  # A dicitonary of start_frame: set(movements)
        self.colours = {}  # A dicitonary of start_frame: set(colours)
        self.all_vectors = set()  # A set of all possible movements
        self.all_colours = set()  # A set of all possible colours
        self.img_data = []  # A list of data for html/xml generation

        self.ready = True  # Can be processed

        if not os.path.exists(self.picpath):
            os.mkdir(self.picpath)
        if os.path.exists(self.htmlpath):
            msg = ("Scene indexes for this video (%s) alredy exist."
                   "Continuing will overwrite them."
                   "Do you want to continue?") % self.vidfn
            title = "Existing files detected!"
            if skip:
                self.ready = False
                print "%s is already processed, skipping." % self.vidfn
            elif overwrite or tkMessageBox.askyesno(title, msg):
                return
            else:
                self.ready = False
                print "Processing cancelled for %s." % self.vidfn

    def open_video(self):
        """Find a compatible Avisynth import method for the given file.
            TODO: Add other sources? qtsource?
        """
        sources = [
            'AVISource("%(vidfn)s")',
            'LoadPlugin("%(rpath)s\\ffms2.dll")\nFFVideoSource("%(vidfn)s")',
        ]

        for source in sources:
            try:
                script = source % {"vidfn": self.vidpath, "rpath": self.rpath}
                with AvisynthHelper(script) as clip:
                    self.get_vid_info(clip)
            except avisynth.AvisynthError as e:
                if not __debug__:
                    print e
                    print "Trying alternate methods"
            else:
                return script
        raise Exception("Cannot open video file %s" % self.vidpath)

    def get_vid_info(self, clip):
        """Store important information about this avisynth clip"""
        self.vid_info = {
                        "framecount": int(clip.Framecount),
                        "width": int(clip.Width),
                        "height": int(clip.Height),
                        "fps_num": int(clip.FramerateNumerator),
                        "fps_den": int(clip.FramerateDenominator),
                    }

    @is_ready
    def scene_detection(self):
        """Use SCXvid to generate a list of scene keyframes.
        Simlutaneously, using MDepan to log the motion vectors."""

        keylog = os.path.join(self.picpath, "keyframes.log")
        mvlog = os.path.join(self.picpath, "vectors.log")
        script = (
            'LoadPlugin("%(rpath)s\\SCXvid.dll")'
            'LoadPlugin("%(rpath)s\\mvtools2.dll")'
            '%(source)s'
            'BilinearResize(8 * int((240 * last.width/last.height) / 8), 240)'
            'ConvertToYV12()'
            'SCXvid("%(keylog)s")'
            'vectors = MSuper().MAnalyse()'
            'MDepan(vectors, log="%(mvlog)s")'
        ) % {"rpath": self.rpath,
            "ppath": self.picpath,
            "vidfn": self.vidfn,
            "source": self.source,
            "keylog": keylog,
            "mvlog": mvlog}

        with AvisynthHelper(script) as clip:
            # Store information about the clip for later
            self.get_vid_info(clip)
            framecount = self.vid_info["framecount"]

            widgets = [
                        '(1/2) Scene Detection: ', pb.Percentage(),
                        ' ', pb.Bar(marker=pb.RotatingMarker()),
                        ' ', pb.ETA()
                      ]
            pbar = pb.ProgressBar(widgets=widgets, maxval=framecount).start()

            for frame in range(framecount):
                clip._GetFrame(frame)
                pbar.update(frame)
            pbar.finish()

        self.scenes = self.read_scenes(keylog)
        vdata = []
        with open(mvlog, "r") as mv:
            vdata = mv.readlines()
        self.all_vectors, self.vectors = self.read_vectors(self.scenes, vdata)

        return self.scenes, self.vectors

    def read_vectors(self, scenes, vdata):
        """Analyse MDepan's output per scene.

        Depan logs follow the deshaker format with each line printing:

        Frame number - Frame number of the source video. For interlaced video,
                       the frame number will have an 'A' or 'B' appended,
                       depending on the field.
        Pan X - The number of horizontal panning pixels between
                (the middle line of) the previous frame and current frame.
        Pan Y - The number of vertical panning pixels between
                (the middle line of) the previous frame and current frame.
        Rotation - The number of degrees of rotation between
                (the middle line of) the previous frame and current frame.
        Zoom - The zoom factor between (the middle line of) the previous
               frame and current frame.
        """
        all_movements = set()
        scene_vect = defaultdict(list)
        for start, end in scenes:
            vx = 0.
            vy = 0.
            vr = 0.
            vz = 100.
            for i in range(start, end + 1):
                if i >= len(vdata):
                    break
                bits = vdata[i].split()
                if bits and len(bits) >= 5:
                    vx += float(bits[1])
                    vy += float(bits[2])
                    vr += float(bits[3])
                    vz *= float(bits[4])
            if abs(vx) > (self.vid_info["width"] / 10.):
                scene_vect[start].append("m3_left" if vx < 0 else "m4_right")
            if abs(vy) > (self.vid_info["height"] / 10.):
                scene_vect[start].append("m2_down" if vy > 0 else "m1_up")
            if abs(vr) > 10:
                scene_vect[start].append("m6_ccw" if vr > 0 else "m5_cw")
            if not (vz > 90 and vz < 110):
                scene_vect[start].append("m8_out" if vz > 100 else "m7_in")
            if scene_vect[start]:
                all_movements = all_movements | set(scene_vect[start])
        return all_movements, scene_vect

    def read_scenes(self, fn):
        """Get all the keyframes from the log file. Store them and the time
        they occurred in the video."""
        keyframes = [0]
        endframes = []
        with open(fn, "r") as log:
            # The log file starts with 3 unneeded lines
            for i, line in enumerate(log.readlines()[3:]):
                # Minimum scene length in frames
                min_slength = 10
                if line.startswith("i") and (i - keyframes[-1]) > min_slength:
                    keyframes.append(i)
                    endframes.append(i - 1)
        if not endframes:
            raise Exception("Error: video file only had once scene :(")
        # Make sure we add the last scene
        if endframes[-1] != self.vid_info["framecount"]:
            keyframes.append(endframes[-1] + 1)
            endframes.append(self.vid_info["framecount"])
        self.scenes = zip(keyframes, endframes)

        for scene in self.scenes:
            for frame in scene:
                fps_den = self.vid_info["fps_den"]
                fps_num = self.vid_info["fps_num"]
                self.times[frame] = float(frame) * fps_den / fps_num
        return self.scenes

    def get_timestamp(self, frame):
        """Return timestamp for a particular frame."""
        time = self.times[frame]
        return "%02i:%02i:%02i.%02i" % (time // 3600,
                                        time // 60 % 60,
                                        time % 60,
                                        100 * (time % 1))

    @is_ready
    def phase_two(self):
        """This phase simlutaneously does many things:
        1. Find the most common colours in the scene
        2. Look for faces
        3. Writes the jpeg filmstrips
        """

        script = (
            '%(source)s'
            'BilinearResize(8 * int((240 * last.width/last.height) / 8), 240)'
        ) % {"source": self.source}

        self.img_data = []
        self.colours = defaultdict(set)
        self.all_colours = set()

        with AvisynthHelper(script) as clip:
            widgets = ['(2/2) Scene Analysis:  ',
                       pb.Percentage(),
                       ' ',
                       pb.Bar(marker=pb.RotatingMarker()),
                       ' ',
                       pb.ETA()]
            pbar = pb.ProgressBar(widgets=widgets,
                                  maxval=len(self.scenes)).start()
            for n, scene in enumerate(self.scenes):
                start, end = scene
                pbar.update(n)
                images = []

                for i, frame in enumerate(takespread(range(start, end + 1), 4)):
                    npa = get_numpy(clip, frame)
                    images.append(npa)
                    # Facial recognition
                    if "has_face" not in self.vectors[start]:
                        # Copy the image for facial analysis
                        new = numpy.empty_like(npa)
                        new[:] = npa
                        if face.detect(new):
                            self.vectors[start].append("has_face")
                            self.all_vectors.add("has_face")
                    # Quantize the image, find the most common colours
                    for c in most_frequent_colours(npa, top=5):
                        colour = get_colour_name(c[:3])
                        self.colours[start].add(colour)
                        self.all_colours.add(colour)
                # Generate and save the filmstrip
                stacked = numpy.concatenate(images, axis=0)
                img_path = self.get_scene_img_path(start, end)
                Image.fromarray(stacked).save(img_path)
                pbar.update(n)
            pbar.finish()
        self.all_vectors = [x.split("_")[-1] for x in sorted(self.all_vectors)]
        self.img_data = self.get_img_data()

    def get_scene_img_path(self, start, end):
        return os.path.join(self.picpath, "scene_%i_%i.jpg" % (start, end))

    def get_img_data(self):
        """For each scene track a number of items for use by
        html and xml exporters"""
        data = []
        for i, scene in enumerate(self.scenes):
            start, end = scene
            folder = os.path.split(self.picpath)[-1]
            fn = "%s/scene_%i_%i.jpg" % (folder, start, end)
            ts = "%s - %s" % (self.get_timestamp(start),
                              self.get_timestamp(end))
            colours = [kelly_colours[c][0] for c in self.colours[start]]
            data.append({
                "i": i,
                "filename": fn,
                "vidpath": self.vidpath,
                "colours": colours,
                "vectors": [x.split("_")[-1] for x in self.vectors[start]],
                "start": start,
                "end": end,
                "ts": ts,
                "size": (self.vid_info["width"], self.vid_info["height"]),
                "title": "Scene %i, frames %i to %i,  %s with colours %s" % (i,
                    start, end, ts, ", ".join(colours)),
            })
        return data

    @is_ready
    def output_html(self):
        """Render an html file using jinja2 based on the scene information."""
        if not self.img_data:
            return
        template_file = os.path.join(self.rpath, "template.html")
        template = Template(open(template_file, "r").read())

        # Copy icons and javascript to picdir
        if not os.path.exists(os.path.join(self.picpath, "icons")):
            shutil.copytree(os.path.join(self.rpath, "icons"),
                            os.path.join(self.picpath, "icons"))
        for js in ['jquery-1.10.1.min.js']:
            if not os.path.exists(os.path.join(self.picpath, js)):
                shutil.copy2(os.path.join(self.rpath, js),
                             os.path.join(self.picpath, js))

        vidhtml = os.path.join(self.vidroot, "%s.html" % self.vidname)
        with open(vidhtml, "w") as f:
            k_colours = []
            sort_colours = sorted(kelly_colours.items(), key=lambda t: t[1][2])
            for colour, items in sort_colours:
                name = items[0]
                k_colours.append((name, colour, colour in self.all_colours))

            options = {
                "img_data": self.img_data,
                "k_colours": k_colours,
                "all_vectors": ["up", "down", "left", "right",
                                "cw", "ccw", "in", "out", "face"],
                "used_vectors": self.all_vectors,
                "dir": os.path.split(self.picpath)[-1],
                "vidfn": self.vidfn,
                "icon_key": {
                            "up": "Pan up",
                            "down": "Pan down",
                            "left": "Pan left",
                            "right": "Pan right",
                            "cw": "Clockwise rotation",
                            "ccw": "Counter-clockwise rotation",
                            "in": "Zoom in",
                            "out": "Zoom out",
                            "has_face": "Contains faces",
                            "no_face": "Does not contain faces",
                            "reset": "Reset all options",
                        },
            }
            f.write(template.render(options))

    @is_ready
    def output_xml(self):
        """Produce a Final Cut Pro .xml file for importing into programs.
        Only tested with Premiere CS6 currently."""
        if not self.img_data:
            return
        xml = make_xml(self.vidpath, self.img_data)
        xmlfile = os.path.join(self.vidroot, "%s.xml" % self.vidname)
        with open(xmlfile, "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE xmeml>')
            xml.write(f)

    @is_ready
    def run(self, html=True, xml=True, popups=True):
        if not (self.scenes and self.vectors):
            self.scene_detection()
        if not self.img_data:
            self.phase_two()
        if self.img_data:
            if html:
                self.output_html()
            if xml:
                self.output_xml()
        if os.path.exists(self.htmlpath) and popups:
            webbrowser.open(self.htmlpath, new=2)


def get_valid_files(path):
    files = []

    if not os.path.isdir(path):
        return files

    for fn in os.listdir(path):
        if os.path.splitext(fn)[-1] in valid_filetypes:
            files.append(os.path.join(path, fn))

    if not files:
        raise Exception("%s does not contain any valid vid fies." % path)
    return files


def ask_for_file():
    # Present a file chooser dialog
    foptions = {}
    foptions['initialdir'] = my_documents
    foptions['title'] = 'Choose a video file to analyse...'
    foptions['filetypes'] = [('all files', '.*')]
    for ext in valid_filetypes:
        match = ('video files', "*%s" % ext)
        foptions['filetypes'].append(match)
    return tkFileDialog.askopenfilename(**foptions)


def main():
    """Handle default processing for standalone and command-line usage."""
    # Surpress TKinter main window
    root = Tkinter.Tk()
    root.withdraw()

    #Set the icon for dialogs
    icon = os.path.realpath(os.path.join(basedir, "resources", "scenic.ico"))
    root.wm_iconbitmap(icon)

    arguments = docopt(__doc__, version='%s' % version_string)

    silent = arguments.get("--silent")
    if silent:
        # Consume all messages
        class Consume(object):
            def write(self):
                pass
        sys.stdout = Consume()

    # Get the vid or vids to process
    vpath = arguments.get("<PATH>") or ask_for_file()

    # Set up options for running the analyser
    analyser_kwargs = {
        "skip": arguments.get("--skip"),
        "overwrite": arguments.get("--overwrite"),
    }
    run_kwargs = {
        "xml": not arguments.get("--no-xml"),
        "popups": not arguments.get("--no-popups"),
    }

    if not vpath:
        raise Exception("No vid supplied.")
    elif os.path.isdir(vpath):
        vids = get_valid_files(vpath)
    elif not os.path.isfile(vpath):
        raise Exception("'%s' is not a valid path or video file." % vpath)
    else:
        vids = [vpath]

    for i, vid in enumerate(vids, 1):
        if len(vids) > 1:
            print "::: Batch mode: file %s of %s:::" % (i, len(vids))
        if not __debug__:
            try:
                Analyser(vid, **analyser_kwargs).run(**run_kwargs)
            except Exception as e:
                print "Error while analysing %s: %s" % (vid, e)
                continue
        else:
            Analyser(vid, **analyser_kwargs).run(**run_kwargs)
        if len(vids) > 1:
            print ""

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        try:
            main()
        except Exception as e:
            tkMessageBox.showerror(
                " Error",
                ("The program has failed :( "
                 "but it left you this message:\n\n%s") % e
            )
    else:
        main()

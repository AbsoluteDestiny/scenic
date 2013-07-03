"""Scenic: Scene colour and motion analysis for video files.
Pass in a file or a directory of files for analysis.

Usage:
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
from multiprocessing import Queue, cpu_count, freeze_support, active_children

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
from frozen_process import Process


version_string = ""
frozen_version = os.path.join(basedir, "frozen_version.txt")
try:
    if getattr(sys, 'frozen', False):
        version_string = open(frozen_version, "r").read().strip()
    else:
        version_string = "%s" % check_output(['git', 'describe'])
except:
    pass

# Change the console title
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


def mp_image_process(script, input, output):
    """With a script string and two multiprocessing
    queues, will allow batch avs frame getting
    operations spread across many cpus!"""
    with AvisynthHelper(script) as clip:
        for foo, start, end in iter(input.get, 'STOP'):
            result = foo.process_images(clip, start, end)
            output.put(result)


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
        arrnew = arrnew.reshape(-1, 4)  # Array of [[A, R, G, B], ...]
        arrnew = numpy.delete(arrnew, 0, 1)  # Remove the alpha channels
        arrnew = arrnew.reshape(avs.Height, avs.bmih.biWidth, 3)
        arrnew = numpy.fliplr(arrnew)
        return arrnew


def is_ready(func):
    """Only process an instance function if the instance has the attr
    ready set to something truthy."""
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
        self.env.SetMemoryMax(8)

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

    def __init__(self, vidpath, skip=False, overwrite=False, frames=4,
                 min_slength=10, faceprec=1, num_colours=6, nocol=False,
                 nomo=False, noface=False, cpus=0):
        if not vidpath:
            raise Exception("Analyser must have a vid path.")
        self.vidpath = vidpath
        self.skip = skip  # Whether we should skip already-processed files
        self.overwrite = overwrite  # Whether we should overwrite files
        self.samplesize = frames
        self.min_slength = min_slength
        self.num_colours = num_colours  # Number of colours to detect
        self.faceprec = faceprec  # Proces 1 in N frames for facial recognition
        self.nocol = nocol  # Disables colour matching
        self.nomo = nomo    # Disables motion analysis
        self.noface = noface  # Disables face recognition
        self.rpath = os.path.realpath(os.path.join(basedir, "resources"))
        self.vidfn = os.path.split(vidpath)[1]
        self.vidname = os.path.splitext(self.vidfn)[0]
        self.vidroot = os.path.split(vidpath)[0]
        self.picpath = os.path.join(self.vidroot, "Scenes_%s" % self.vidname)
        self.htmlpath = os.path.join(self.vidroot, "%s.html" % self.vidname)
        self.xmlpath = os.path.join(self.vidroot, "%s.xml" % self.vidname)
        self.vid_info = {}
        self.source = self.open_video()
        self.cpus = cpu_count()
        if cpus:
            self.cpus = min(cpus, self.cpus)

        print "Processing video %s" % (self.vidfn)

        self.scenes = []  # A list of (start, end) frames
        self.times = {}  # A dictionary of frame: time in seconds
        self.vectors = {}  # A dicitonary of start_frame: set(movements)
        self.colours = {}  # A dicitonary of start_frame: set(colours)
        self.all_vectors = set()  # A set of all possible movements
        self.all_colours = set()  # A set of all possible colours
        self.img_data = []  # A list of data for html/xml generation

        self.ready = True  # Can be processed
        self.check_output_files()

    def check_output_files(self):
        """Make directories if they do not exist already. Check to see if we
        have processed this file before."""
        check_paths = [self.htmlpath, self.picpath, self.xmlpath]
        if any(os.path.exists(p) for p in check_paths):
            msg = ("Scene indexes for this video already exist:\n\n'%s'\n\n"
                   "Continuing will overwrite them. "
                   "Do you want to continue?") % self.vidfn
            title = "Existing files detected!"
            if self.skip:
                self.ready = False
                print "%s is already processed, skipping." % self.vidfn
            elif self.overwrite or tkMessageBox.askyesno(title, msg):
                # Safe to overwrite all files
                if not os.path.exists(self.picpath):
                    os.mkdir(self.picpath)
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
            'LoadPlugin("%(rpath)s\\SCXvid.dll")\n'
            'LoadPlugin("%(rpath)s\\mvtools2.dll")\n'
            '%(source)s'
            'BilinearResize(8 * int((240 * last.width/last.height) / 8), 240)\n'
            'ConvertToYV12()\n'
            'SCXvid("%(keylog)s")\n'
            )
        if not self.nomo:
            script += (
                'vectors = MSuper().MAnalyse()\n'
                'MDepan(vectors, log="%(mvlog)s")'
            )
        script = script % {"rpath": self.rpath,
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
        if not self.nomo:
            with open(mvlog, "r") as mv:
                vdata = mv.readlines()
                self.all_vectors, self.vectors = self.read_vectors(self.scenes,
                                                                   vdata)

        return

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
                slength = (i - keyframes[-1])
                if line.startswith("i") and slength >= self.min_slength:
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
        1. Finds the most common colours in the scene
        2. Looks for faces
        3. Writes the jpeg filmstrips
        """
        script = (
            '%(source)s'
            'BilinearResize(8 * int((240 * last.width/last.height) / 8), 240)'
        ) % {"source": self.source}

        self.img_data = []
        self.colours = defaultdict(set)
        self.all_colours = set()

        widgets = ['(2/2) Scene Analysis:  ',
                   pb.Percentage(),
                   ' ',
                   pb.Bar(marker=pb.RotatingMarker()),
                   ' ',
                   pb.ETA()]
        pbar = pb.ProgressBar(widgets=widgets,
                              maxval=len(self.scenes)).start()

        # Create queues
        task_queue = Queue()
        done_queue = Queue()

        # Submit tasks
        for start, end in self.scenes:
            task_queue.put((self, start, end))

        # Start worker processes
        for i in range(self.cpus):
            args = (script, task_queue, done_queue)
            Process(target=mp_image_process, args=args).start()

        # Get and print results
        for i, scene in enumerate(self.scenes):
            start, has_face, colours = done_queue.get()
            if has_face:
                self.vectors[start].append("has_face")
                self.all_vectors.add("has_face")
            for colour in colours:
                self.colours[start].add(colour)
                self.all_colours.add(colour)
            pbar.update(i)

        # Stop the queues
        for i in range(self.cpus):
            task_queue.put('STOP')

        pbar.finish()
        self.all_vectors = [x.split("_")[-1] for x in sorted(self.all_vectors)]
        self.img_data = self.get_img_data()

    def process_images(self, clip, start, end):
        has_face = False
        colours = set()
        images = []
        sample = takespread(range(start, end + 1), self.samplesize)
        for i, frame in enumerate(sample):
            npa = get_numpy(clip, frame)
            images.append(npa)

            # Should we skip facial recognition?
            if self.noface or i % self.faceprec:
                continue

            # Facial recognition
            if not has_face:
                # Copy the image for facial analysis
                new = numpy.empty_like(npa)
                new[:] = npa
                if face.detect(new):
                    has_face = True
        # Generate and save the filmstrip
        stacked = numpy.concatenate(images, axis=0)
        img_path = self.get_scene_img_path(start, end)
        img = Image.fromarray(stacked)
        img.save(img_path)
        if not self.nocol:
            # Quantize the image, find the most common colours
            for c in most_frequent_colours(img, top=self.num_colours):
                colour = get_colour_name(c[:3])
                colours.add(colour)
        return (start, has_face, colours)

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
            title = "Scene %i, frames %i to %i,  %s" % (i, start, end, ts)
            if not self.nocol:
                title += " with colours %s" % (", ".join(colours))
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
                "title": title,
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
            if self.nocol:
                k_colours = []

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
        xmlfile = self.xmlpath
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


def get_cl_args():
    """"
    Process the command line arguments and parse them for use.
    """
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

    frames = arguments.get("--frames").strip()
    if frames.isdigit() == False or int(frames) < 1:
        raise Exception("--frames must be an integer >= 1")
    frames = int(frames)

    min_slength = arguments.get("--minscene").strip()
    if min_slength.isdigit() == False or int(min_slength) < frames:
        raise Exception("--minscene must be an integer that is >= --frames")
    min_slength = int(min_slength)

    faceprec = arguments.get("--faces").strip()
    if faceprec.isdigit() == False or int(faceprec) > frames:
        raise Exception("--minscene must be an integer that is <= --frames")
    faceprec = int(faceprec)

    colours = arguments.get("--colours").strip()
    if colours.isdigit() == False or int(colours) < 1:
        raise Exception("--colours must be an integer >= 1")
    colours = int(colours)

    cpus = arguments.get("--cpus")
    if cpus:
        cpus = cpus.strip()
        if cpus.isdigit() == False or int(cpus) < 1:
            raise Exception("--cpus must be an integer >= 1")
        cpus = int(cpus)

    # Set up options for running the analyser
    analyser_kwargs = {
        "skip": arguments.get("--skip"),
        "overwrite": arguments.get("--overwrite"),
        "nocol": arguments.get("--no-colours"),
        "nomo": arguments.get("--no-motion"),
        "noface": arguments.get("--no-face"),
        "frames": frames,
        "min_slength": min_slength,
        "faceprec": faceprec,
        "num_colours": colours,
        "cpus": cpus,
    }
    run_kwargs = {
        "xml": not arguments.get("--no-xml"),
        "popups": not arguments.get("--no-popups"),
    }
    return vpath, analyser_kwargs, run_kwargs


def main():
    """Handle default processing for standalone and command-line usage."""
    # Surpress TKinter main window
    root = Tkinter.Tk()
    root.withdraw()

    #Set the icon for dialogs
    icon = os.path.realpath(os.path.join(basedir, "resources", "scenic.ico"))
    root.wm_iconbitmap(icon)

    vpath, analyser_kwargs, run_kwargs = get_cl_args()

    if not vpath:
        raise Exception("No vid supplied.")
    elif isinstance(vpath, list):
        vids = [p for p in vpath if os.path.splitext(p)[-1] in valid_filetypes]
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
        freeze_support()
        try:
            main()
        except Exception as e:
            tkMessageBox.showerror(
                " Error",
                ("The program has failed :( "
                 "but it left you this message:\n\n%s") % e
            )
        # We need to wait for all child processes otherwise
        # --onefile mode won't work.
        while active_children():
            active_children()[0].join()
    else:
        main()

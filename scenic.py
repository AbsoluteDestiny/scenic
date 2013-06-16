import sys
import os

if getattr(sys, 'frozen', False):
    # we are running in a |PyInstaller| bundle
    basedir = sys._MEIPASS
else:
    # we are running in a normal Python environment
    basedir = os.path.dirname(__file__)

import ctypes
import ctypes.wintypes
import shutil
import webbrowser
from collections import defaultdict
from math import ceil
import Tkinter
import tkMessageBox
import tkFileDialog

import numpy
import scipy.misc
import progressbar as pb
import face
from jinja2 import Template

from avisynth.pyavs import AvsClip
from avisynth import avisynth
from color import get_colour_name, most_frequent_colours, kelly_colours
from xmlgen import make_xml


app_name = "Scenic: Movie Scene Detection and Analysis"
buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
ctypes.windll.shell32.SHGetFolderPathW(0, 5, 0, 0, buf)
my_documents = buf.value
ctypes.windll.kernel32.SetConsoleTitleA(app_name)


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

    def __init__(self, vidpath):
        if not vidpath:
            raise Exception("Analyser must have a vid path.")
        self.vidpath = vidpath
        self.rpath = os.path.realpath(os.path.join(basedir, "resources"))
        self.vidfn = os.path.split(vidfn)[1]
        self.vidname = os.path.splitext(self.vidfn)[0]
        self.vidroot = os.path.split(vidfn)[0]
        self.picpath = os.path.join(self.vidroot, "Scenes_%s" % self.vidname)
        self.htmlpath = os.path.join(self.vidroot, "%s.html" % self.vidname)
        self.vid_info = {}
        self.source = self.open_video()

        print "Processing video %s" % (os.path.split(vidfn)[-1])

        self.scenes = []  # A list of (start, end) frames
        self.times = {}  # A dictionary of frame: time in seconds
        self.vectors = {}  # A dicitonary of start_frame: set(movements)
        self.colours = {}  # A dicitonary of start_frame: set(colours)
        self.all_vectors = set()  # A set of all possible movements
        self.all_colours = set()  # A set of all possible colours
        self.img_data = []  # A list of data for html/xml generation

        if not os.path.exists(self.picpath):
            os.mkdir(self.picpath)
        if os.path.exists(self.htmlpath):
            msg = ("Scene indexes for this video (%s) alredy exist."
                   "Continuing will overwrite them."
                   "Do you want to continue?") % self.vidfn
            title = "Existing files detected!"
            if tkMessageBox.askyesno(title, msg):
                pass
            else:
                print "Processing cancelled."
                sys.exit(0)

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
            'ConvertToYUY2()'
            'SCXvid("%(keylog)s")'
            'vectors = MSuper().MAnalyse(isb = false)'
            'MDepan(vectors, log="%(mvlog)s", range=1)'
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
        """Analyse MDepan's output per scene"""
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
            for i, line in enumerate(log, -2):
                if line.startswith("i") and (i - keyframes[-1]) > 10:
                    keyframes.append(i)
                    endframes.append(i - 1)
        if not endframes:
            raise Exception("Error: video file only had once scene :(")
        self.scenes = zip(keyframes, endframes)
        self.scenes.append((self.scenes[-1][-1], self.vid_info["framecount"]))
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
            widgets = ['(2/2) Scene Analysis: ',
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

                for i, frame in enumerate(takespread(range(start, end + 1), 5)):
                    npa = get_numpy(clip, frame)
                    images.append(npa)
                    # Copy the image for facial analysis
                    new = numpy.empty_like(npa)
                    new[:] = npa
                    if i in [0, 2, 5]:
                        #Facial recognition
                        if face.detect(new):
                            self.vectors[start].append("has_face")
                            self.all_vectors.add("has_face")
                        # Quantize the image, find the most common colours
                        for c in most_frequent_colours(npa, top=5):
                            colour = get_colour_name(c[:3])
                            self.colours[start].add(colour)
                            self.all_colours.add(colour)
                    pbar.update(n)
                # Generate and save the filmstrip
                stacked = numpy.concatenate(images, axis=0)
                img_path = self.get_scene_img_path(start, end)
                scipy.misc.imsave(img_path, stacked)
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

    def output_xml(self):
        """Produce a Final Cut Pro .xml file for importing into programs.
        Only tested with Premiere CS6 currently."""
        if not self.img_data:
            return
        xml = make_xml(vidfn, self.img_data)
        xmlfile = os.path.join(self.vidroot, "%s.xml" % self.vidname)
        with open(xmlfile, "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE xmeml>')
            xml.write(f)

    def run(self):
        if not (self.scenes and self.vectors):
            self.scene_detection()
        if not self.img_data:
            self.phase_two()
        if self.img_data:
            self.output_html()
            self.output_xml()
        if os.path.exists(self.htmlpath):
            webbrowser.open(self.htmlpath, new=2)

if __name__ == "__main__":
    root = Tkinter.Tk()
    root.withdraw()
    icon = os.path.realpath(os.path.join(basedir, "resources", "scenic.ico"))
    root.wm_iconbitmap(icon)

    # define options for opening or saving a file
    foptions = {}
    foptions['filetypes'] = [('all files', '.*'),
                             ('video files', "*.avi"),
                             ('video files', "*.avs"),
                             ('video files', "*.dv"),
                             ('video files', "*.flv"),
                             ('video files', "*.m2v"),
                             ('video files', "*.m4v"),
                             ('video files', "*.mkv"),
                             ('video files', "*.mov"),
                             ('video files', "*.mp4"),
                             ('video files', "*.mpg"),
                             ('video files', "*.ogv"),
                             ('video files', "*.vob"),
                             ('video files', "*.webm"),
                             ('video files', "*.wmv")]
    foptions['title'] = 'Choose a video file to analyse...'
    foptions['initialdir'] = my_documents
    vidfn = tkFileDialog.askopenfilename(**foptions)
    if not __debug__:
        try:
            anal = Analyser(vidfn)
            anal.run()
        except Exception as e:
            tkMessageBox.showerror(
                " Error",
                ("The program has failed :( "
                 "but it left you this message:\n\n%s") % e
            )
    else:
        anal = Analyser(vidfn)
        anal.run()

import os
import xml.etree.cElementTree as ET
import re
import uuid
import urlparse
import urllib

from mediainfo.MediaInfoDLL import *
MI = MediaInfo()
Version = MI.Option_Static("Info_Version",
                            "0.7.7.0;MediaInfoDLL_Example_Python;0.7.7.0")
if Version == "":
    print "\nMediaInfo.Dll: this version of the DLL is not compatible"

pattern = re.compile('[\W_]+')

clip_counter = 0
subclip_counter = 0


def path2url(path):
    return urlparse.urljoin('file:', urllib.pathname2url(path))


def batch_node(items, parent):
    for node, text in items:
        thing = ET.SubElement(parent, node)
        thing.text = text


def make_clip_xml(fn, parent, finfo, inframe=None, outframe=None, name=None):
    global clip_counter
    global subclip_counter
    clip_counter += 1
    mclip_id = "masterclip-%i" % (clip_counter)

    clip = ET.SubElement(parent, "clip", id=mclip_id, frameBlend="FALSE")
    subitems = [
        ("uuid", str(uuid.uuid1())),
        ("masterclipid", mclip_id),
        ("ismasterclip", "TRUE"),
        ("duration", finfo["duration"]),
        ("name", name or os.path.split(fn)[-1]),
    ]
    if inframe or outframe:
        subitems += [("in", str(inframe)), ("out", str(outframe))]

    batch_node(subitems, clip)
    rate = ET.SubElement(clip, "rate")
    tb = ET.SubElement(rate, "timebase")
    tb.text = finfo["timebase"]

    media = ET.SubElement(clip, "media")

    # Video Track
    video = ET.SubElement(media, "video")
    vtrack = ET.SubElement(video, "track")
    subclip_counter += 1
    vcitem = ET.SubElement(vtrack, "clipitem",
                id="clipitem-%i" % subclip_counter,
                frameBlend="FALSE")
    subitems = [
        ("masterclipid", mclip_id),
        ("name", name or os.path.split(fn)[-1]),
        ("alphatype", finfo["alpha"]),
        # ("pixelaspectratio", finfo["par"]),
        # ("anamorphic", finfo["anamorphic"]),
        ]

    batch_node(subitems, vcitem)
    vfile = ET.SubElement(vcitem, "file", id="file-%i" % clip_counter)

    rate = ET.SubElement(vfile, "rate")
    tb = ET.SubElement(rate, "timebase")
    tb.text = finfo["timebase"]

    pathurl = urllib.quote(urllib.pathname2url(fn))
    pathurl = pathurl.replace("///", "file://localhost/")
    subitems = [
        ("name", name or os.path.split(fn)[-1]),
        ("pathurl", pathurl),
        ("duraiton", finfo["duration"]),
    ]
    batch_node(subitems, vfile)

    submedia = ET.SubElement(vfile, "media")
    mvideo = ET.SubElement(submedia, "video")
    schar = ET.SubElement(mvideo, "subcharacteristics")
    rate = ET.SubElement(schar, "rate")
    tb = ET.SubElement(rate, "timebase")
    tb.text = finfo["timebase"]
    subitems = [
        ("width", finfo["width"]),
        ("height", finfo["height"]),
        # ("anamorphic", finfo["anamorphic"]),
        # ("pixelaspectratio", finfo["par"]),
        ("fielddominance", finfo["FO"]),
    ]
    batch_node(subitems, schar)

    maudio = ET.SubElement(submedia, "audio")
    batch_node([("chanelcount", "2")], maudio)
    schar = ET.SubElement(maudio, "subcharacteristics")
    rate = ET.SubElement(schar, "rate")
    tb = ET.SubElement(rate, "timebase")
    tb.text = finfo["timebase"]
    subitems = [
        ("depth", finfo["adepth"]),
        ("samplerate", finfo["asamrate"]),
    ]
    batch_node(subitems, schar)

    # Audio Channels
    audio = ET.SubElement(media, "audio")
    for channel in range(2):
        atrack = ET.SubElement(audio, "track")
        subclip_counter += 1
        acitem = ET.SubElement(atrack,
                               "clipitem",
                               id="clipitem-%s" % subclip_counter,
                               frameBlend="FALSE")
        masterc = ET.SubElement(acitem, "masterclip")
        masterc.text = mclip_id
        name = ET.SubElement(acitem, "name")
        name.text = name or name or os.path.split(fn)[-1]
        ET.SubElement(acitem, "file", id="file-%i" % clip_counter)
        strack = ET.SubElement(acitem, "sourcetrack")
        subitems = [('mediatrack', "audio"), ("trackindex", str(channel))]
        batch_node(subitems, strack)

    return clip


def make_xml(fn, scenes):
    """Given a source file and a list of scene data, generate a
    Final Cut Pro xml project."""
    MI.Open(fn)
    finfo = {
        "duration": MI.Get(Stream.Video, 0, u"FrameCount"),
        "timebase": "%i" % round(float(MI.Get(Stream.Video, 0, u"FrameRate"))),
        "alpha": "none",
        # "par": "square",
        # "anamporphic": "",
        "FO": "lower",
        "width": MI.Get(Stream.Video, 0, u"Width"),
        "height": MI.Get(Stream.Video, 0, u"Height"),
        "adepth": MI.Get(Stream.Audio, 0, u"Resolution"),
        "asamrate": MI.Get(Stream.Audio, 0, u"SamplingRate"),
    }

    root = ET.Element("xmeml", version="4")

    project = ET.SubElement(root, "project")

    name = ET.SubElement(project, "name")
    name.text = "Test Project"

    children = ET.SubElement(project, "children")

    scene_bin = ET.SubElement(children, "bin")
    scene_bin_name = ET.SubElement(scene_bin, "name")
    scene_bin_name.text = "Scenes"

    bin_kids = ET.SubElement(scene_bin, "children")

    # Add the main clip
    make_clip_xml(fn, children, finfo)
    for i, item in enumerate(scenes):
        make_clip_xml(item["vidpath"], bin_kids, finfo,
                      inframe=item["start"], outframe=item["end"],
                      name=item["title"])
    tree = ET.ElementTree(root)
    return tree

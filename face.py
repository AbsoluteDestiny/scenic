import sys
import os

if getattr(sys, 'frozen', False):
    # we are running in a |PyInstaller| bundle
    basedir = sys._MEIPASS
else:
    # we are running in a normal Python environment
    basedir = os.path.dirname(__file__)

import cv

cascades = [
    cv.Load(os.path.join(basedir,
                         'haarcascades/haarcascade_frontalface_alt.xml')),
    cv.Load(os.path.join(basedir,
                         'haarcascades/haarcascade_profileface.xml')),
]


def detect(img):
    """Return list of faces detected in a numpy array"""
    img = cv.fromarray(img)
    rects = []
    for cascade in cascades:
        options = (img, cascade, cv.CreateMemStorage(0), 1.3, 4, 0, (20, 20))
        rects = cv.HaarDetectObjects(*options)
        if rects:
            return rects
    return rects

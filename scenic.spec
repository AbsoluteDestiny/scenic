# -*- mode: python -*-

## Store the version in a text file
import os
from subprocess import check_output
fvpath = "frozen_version.txt"
version = check_output(['git', 'describe', '--dirty']).strip()
with open(fvpath, "w") as ver:
  print >> ver, version

#Exclude big modules
big = [
  '_ssl',
  'doctest',
  'pdb',
  'inspect',
]

a = Analysis(['scenic.py'],
             pathex=['C:\\Users\\ian\\Documents\\repos\\scenic'],
             hiddenimports=["numpy", "pywintypes"],
             excludes=big,
             hookspath=None,
             runtime_hooks=None)

pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts + [('O','','OPTION')],
          a.binaries + [(fvpath, "./" + fvpath, 'DATA')],
          a.zipfiles,
          a.datas,
          Tree('./resources', prefix='resources'),
          Tree('./haarcascades', prefix='haarcascades'),
          Tree('./mediainfo', prefix='mediainfo'),
          name='scenic-v%s.exe' % version,
          icon='./resources/scenic.ico',
          debug=False,
          strip=None,
          upx=True,
          console=True )
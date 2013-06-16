# -*- mode: python -*-

## Store the version in a text file
import os
from subprocess import check_output
fvpath = "frozen_version.txt"
with open(fvpath, "w") as ver:
  print >> ver, check_output(['git', 'describe']).strip()

a = Analysis(['scenic.py'],
             pathex=['C:\\Users\\ian\\Documents\\repos\\scenic'],
             hiddenimports=["numpy"],
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
          name='scenic.exe',
          icon='./resources/scenic.ico',
          debug=False,
          strip=None,
          upx=True,
          console=True )
# -*- mode: python -*-
a = Analysis(['scenic.py'],
             pathex=['C:\\Users\\ian\\Documents\\repos\\scenic'],
             hiddenimports=["numpy"],
             hookspath=None,
             runtime_hooks=None)
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts + [('O','','OPTION')],
          a.binaries,
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

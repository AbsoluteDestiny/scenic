import ctypes
import sys
import os

if getattr(sys, 'frozen', False):
    # we are running in a |PyInstaller| bundle
    basedir = sys._MEIPASS
else:
    # we are running in a normal Python environment
    basedir = os.path.dirname(os.path.abspath(sys.argv[0]))

dlldir = os.path.join(basedir, "resources")
os.environ['PATH'] = ';'.join([dlldir, os.environ['PATH']])
avidll = ctypes.windll.LoadLibrary(os.path.join(dlldir, 'avisynth.dll'))


# avidll = ctypes.windll.avisynth
    
#constants
PLANAR_Y=1<<0
PLANAR_U=1<<1
PLANAR_V=1<<2
PLANAR_ALIGNED=1<<3
PLANAR_Y_ALIGNED=PLANAR_Y|PLANAR_ALIGNED
PLANAR_U_ALIGNED=PLANAR_U|PLANAR_ALIGNED
PLANAR_V_ALIGNED=PLANAR_V|PLANAR_ALIGNED

SAMPLE_INT8  = 1<<0
SAMPLE_INT16 = 1<<1
SAMPLE_INT24 = 1<<2
SAMPLE_INT32 = 1<<3
SAMPLE_FLOAT = 1<<4

CS_BGR = 1<<28
CS_YUV = 1<<29
CS_INTERLEAVED = 1<<30
CS_PLANAR = 1<<31

CS_UNKNOWN = 0,
CS_BGR24 = 1<<0 | CS_BGR | CS_INTERLEAVED
CS_BGR32 = 1<<1 | CS_BGR | CS_INTERLEAVED
CS_YUY2 = 1<<2 | CS_YUV | CS_INTERLEAVED
CS_YV12 = 1<<3 | CS_YUV | CS_PLANAR  # y-v-u, planar
CS_I420 = 1<<4 | CS_YUV | CS_PLANAR  # y-u-v, planar
CS_IYUV = 1<<4 | CS_YUV | CS_PLANAR

IT_BFF = 1<<0
IT_TFF = 1<<1
IT_FIELDBASED = 1<<2

FILTER_TYPE=1
FILTER_INPUT_COLORSPACE=2
FILTER_OUTPUT_TYPE=9
FILTER_NAME=4
FILTER_AUTHOR=5
FILTER_VERSION=6
FILTER_ARGS=7
FILTER_ARGS_INFO=8
FILTER_ARGS_DESCRIPTION=10
FILTER_DESCRIPTION=11

FILTER_TYPE_AUDIO=1
FILTER_TYPE_VIDEO=2
FILTER_OUTPUT_TYPE_SAME=3
FILTER_OUTPUT_TYPE_DIFFERENT=4

CACHE_NOTHING=0
CACHE_RANGE=1

CPU_FORCE        = 0x01   # N/A
CPU_FPU          = 0x02   # 386/486DX
CPU_MMX          = 0x04   # P55C, K6, PII
CPU_INTEGER_SSE  = 0x08   # PIII, Athlon
CPU_SSE          = 0x10   # PIII, Athlon XP/MP
CPU_SSE2         = 0x20   # PIV, Hammer
CPU_3DNOW        = 0x40   # K6-2
CPU_3DNOW_EXT    = 0x80   # Athlon
CPU_X86_64       = 0xA0   # Hammer (note: equiv. to 3DNow + SSE2, 

  
FRAME_ALIGN=16


  
#ctypes helper
def ByRefAt(obj,offset):
    #print>>sys.stdout, dir(obj)
    objtype=obj.__class__
    p = ctypes.cast(obj, ctypes.c_void_p)
    p.value += ctypes.sizeof(obj._type_) * offset
    return ctypes.cast(p,objtype)

class AvisynthError(Exception):
    pass

class PIScriptEnvironment:
    #p=ctypes.c_void_p()
    def __init__(self,pin):
        self.p=pin
        self._as_parameter_ = self.p
    def from_param(obj):
        if not isinstance(obj,PIScriptEnvironment):
            raise TypeError("Wrong argument: PIScriptEnvironment expected")
        return obj._as_parameter_
    def Release(self):
        if self.p is not None:
            #print>>sys.stderr, "    Releasing PIScriptEnvironment: ",self
            avs_delete_script_environment(self)
        self.p=None
    def __del__(self):
        #print>>sys.stderr, "del env"
        self.Release()
    def Invoke(self,name,args,arg_names):
        if isinstance(args,list):
            a=(AVS_Value*len(args))()
            for x in range(len(args)):
                a[x]=args[x]
            args=AVS_Value()    
            args.type=97#='a'rray
            args.d.a=ctypes.cast(ctypes.byref(a), ctypes.POINTER(AVS_Value))
            args.array_size=len(a)
        if arg_names==0:
            arg_names=None
        elif isinstance(arg_names,list):
            a=(ctypes.c_char_p*len(arg_names))()
            for x in range(len(arg_names)):
                a[x]=arg_names[x]
            arg_names=ctypes.cast(ctypes.byref(a), ctypes.POINTER(ctypes.c_char_p))
            print arg_names
        retval=avs_invoke(self,name,args,arg_names)
        if retval.type==101: #'e'rror
            raise AvisynthError(retval.d.s)
        else: return retval
    def GetCPUFlags(self):return avs_get_cpu_flags(self)
    def CheckVersion(self,version):return avs_check_version(self,version)
    def SaveString(self,string):return avs_save_string(self,string,len(string))
    def AddFunction(self,name,params,py_function,userdata):
        avs_add_function(self,name,params,APPLYFUNC(py_function),
                         ctypes.ByRef(userdata))
    def FunctionExists(self,name):return avs_function_exists(self,name)
    def GetVar(self,name):
        retval=avs_get_var(self,name)
        if retval.type==0: raise AvisynthError("NotFound")
        else: return retval
    def SetVar(self,name,val):return avs_set_var(self,name,val)
    def SetGlobalVar(self,name,val):return avs_set_global_var(self,name,val)
    def NewVideoFrame(self,vi):
        return avs_new_video_frame_a(self,vi,FRAME_ALIGN)
    def MakeWritable(self,pvideoframe):
        return avs_make_writable(self,ctypes.POINTER(pvideoframe.p))
    def BitBlt(self,dstp,dst_pitch,srcp,src_pitch,row_size,height):
        avs_bit_blt(self,dstp,dst_pitch,srcp,src_pitch,row_size,height)
    def AtExit(self,py_function,userdata):
        return avs_at_exit(self,SHUTDOWNFUNC(py_function),ctypes.POINTER(userdata))
    def SetMemoryMax(self,mem):
        return avs_set_memory_max(self,mem)
    def SetWorkingDir(self,newdir):
        return avs_set_working_dir(self,newdir)
    def Subframe(self,src,rel_offset,new_pitch,new_row_size,new_height):
        return avs_subframe(self,src,rel_offset,new_pitch,new_row_size,new_height)
    def SubframePlanar(self,src,rel_offset,new_pitch,new_row_size,
                       new_height,rel_offsetU,rel_offsetV,new_pitchUV):
        return avs_subframe(self,src,rel_offset,new_pitch,new_row_size,
                            new_height,rel_offsetU,rel_offsetV,new_pitchUV)

    
class VideoInfo(ctypes.Structure):
    _fields_ = [("width",ctypes.c_int),
                ("height",ctypes.c_int),
                ("fps_numerator",ctypes.c_uint),
                ("fps_denominator",ctypes.c_uint),
                ("num_frames",ctypes.c_int),
                ("pixel_type",ctypes.c_int),
                ("audio_samples_per_second",ctypes.c_int),
                ("sample_type",ctypes.c_int),
                ("num_audio_samples",ctypes.c_int64),
                ("nchannels",ctypes.c_int),
                ("image_type",ctypes.c_int)]
    
class PVideoInfo:
    def __init__(self,pin=0):
        if pin==0:
            pin=pointer(VideoInfo())
        self.p=pin
        self._as_parameter_ = self.p
    def from_param(obj):
        if not isinstance(obj,PVideoInfo):
            raise TypeError("Wrong argument: PVideoInfo expected")
        return obj._as_parameter_
    def __getattr__( self, name) :
        return self.p.contents.__getattribute__(name)
    
    def HasVideo(self): return self.width!=0
    def HasAudio(self): return self.audio_samples_per_second!=0
    def IsRGB(self): return self.pixel_type&CS_BGR!=0
    def IsRGB24(self): return (self.pixel_type&CS_BGR24)==CS_BGR24
    def IsRGB32(self): return (self.pixel_type&CS_BGR32)==CS_BGR32
    def IsYUV(self): return self.pixel_type&CS_YUV!=0
    def IsYUY2(self): return (self.pixel_type&CS_YUY2)==CS_YUY2
    def IsYV12(self):
        return ((self.pixel_type&CS_YV12)==CS_YV12) or \
    ((self.pixel_type&CS_I420)==CS_I420)
    def IsColorSpace(self,c_space): return (self.pixel_type&c_space)==c_space
    def IsProperty(self,Property): return (self.pixel_type&Property)==Property
    def IsPlanar(self): return self.pixel_type&CS_PLANAR!=0
    def IsFieldBased(self): return self.image_type&IT_FIELDBASED!=0
    def IsParityKnown(self): return (self.image_type&IT_FIELDBASED!=0) and \
        (self.image_type&(IT_BFF|IT_TFF)!=0)
    def IsBFF(self): return self.image_type&IT_BFF!=0
    def IsTFF(self): return self.image_type&IT_TFF!=0
    def BitsPerPixel(self):
        if self.IsRGB24():return 24
        elif self.IsRGB32():return 32
        elif self.IsYUY2():return 16
        elif self.IsYV12():return 12
        else :return 0
    def BytesFromPixels(self,pixels):return pixels*(self.BitsPerPixel()>>3)
    def RowSize(self): return self.BytesFromPixels(self.width)
    def BMPSize(self):
        if self.IsPlanar():
            p = self.height * ((self.RowSize()+3) & ~3)
            p+=p>>1
            return p
        return self.height * ((self.RowSize()+3) & ~3)
    def SamplesPerSecond(self):return self.audio_samples_per_second
    def BytesPerChannel(self):
        if self.sample_type==SAMPLE_INT8:return ctypes.sizeof(ctypes.c_char)
        elif self.sample_type==SAMPLE_INT16:return ctypes.sizeof(ctypes.c_short)
        if self.sample_type==SAMPLE_INT24:return 3
        if self.sample_type==SAMPLE_INT32:return ctypes.sizeof(ctypes.c_int)
        if self.sample_type==SAMPLE_FLOAT:return ctypes.sizeof(ctypes.c_float)
        return 0
    def BytesPerAudioSample(self):return self.BytesPerChannel()*self.nchannels
    def AudioSamplesFromFrames(self,frames):
        return frames * self.audio_samples_per_second\
        * self.fps_denominator / self.fps_numerator
    def FramesFromAudioSamples(self,samples):
        return samples * self.fps_numerator / self.fps_denominator \
        / self.audio_samples_per_second
    def AudioSamplesFromBytes(self,bytes):
        return bytes/self.BytesPerAudioSample()
    def BytesFromAudioSamples(self,samples):
        return samples*self.BytesPerAudioSample()
    def AudioChannels(self):
        return self.nchannels
    def SampleType(self):
        return self.sample_type
    def SetProperty(self,Property):
        self.image_type|=Property
    def ClearProperty(self,Property):
        self.image_type&=~Property
    def SetFieldBased(self, isfieldbased):
        if isfieldbased: self.image_type|=IT_FIELDBASED
        else: self.image_type&=~IT_FIELDBASED
    def SetFPS(self,numerator,denominator):
        x=numerator
        y=denominator
        while y!=0:
            t=x%y
            x=y
            y=t
        self.fps_numerator=numerator/x
        self.fps_denominator=denominator/x
    def IsSameColorspace(self,vi):
        return (self.pixel_type==vi.pixeltype)or(self.IsYV12()and vi.IsYV12())


    
class PClip:
    def __init__(self,pin):
        self.p=pin
        self._as_parameter_ = self.p

    def from_param(obj):
        if not isinstance(obj,PClip):
            raise TypeError("Wrong argument: PClip expected")
        return obj._as_parameter_
    def Copy(self):
        return avs_copy_clip(self)
    def Release(self):
        if self.p is not None:
            #print>>sys.stdout, "    Releasing PClip: ",self
            avs_release_clip(self.p)
        self.p=None
    def __del__(self):
        self.Release()
    def __call__( self,val):
        self.Release()
        self.p=val.Copy().p
    def GetFrame(self,n): return avs_get_frame(self,n)
    def GetError(self): return avs_clip_get_error(self)
    def GetVideoInfo(self):return avs_get_video_info(self)

        
class VideoFrameBuffer(ctypes.Structure):
    _fields_ = [("data",ctypes.POINTER(ctypes.c_ubyte)),
                ("data_size",ctypes.c_int),
                ("sequence_number",ctypes.c_long),
                ("refcount",ctypes.c_long)]
class VideoFrame(ctypes.Structure):
    _fields_ = [("refcount",ctypes.c_int),
                ("AVS_VideoFrameBuffer",ctypes.POINTER(VideoFrameBuffer)),
                ("offset",ctypes.c_int),
                ("pitch",ctypes.c_int),
                ("row_size",ctypes.c_int),
                ("height",ctypes.c_int),
                ("offsetU",ctypes.c_int),
                ("offsetV",ctypes.c_int),
                ("pitchUV",ctypes.c_int)]


class PVideoFrame:
    #Wrapper for pointer(VideoFrame)
    def __init__(self,pin):
        self.p=pin
        self._as_parameter_ = self.p
    def from_param(obj):
        if not isinstance(obj,PVideoFrame):
            raise TypeError("Wrong argument: PVideoFrame expected")
        return obj._as_parameter_
    def GetPitch(self,plane=PLANAR_Y):
        if plane==PLANAR_Y: return self.p.contents.pitch
        elif plane==PLANAR_U or plane==PLANAR_V:
            return self.p.contents.pitchUV
        return self.p.contents.pitch
    def GetRowSize(self,plane=PLANAR_Y):
        if(plane==PLANAR_Y):return self.p.contents.row_size
        elif plane==PLANAR_U or plane==PLANAR_V:
            if self.p.contents.pitchUV!=0: return self.p.contents.row_size/2
        elif plane==PLANAR_U_ALIGNED or plane==PLANAR_V_ALIGNED:
            r=((self.p.contents.row_size+FRAME_ALIGN-1)&(~(FRAME_ALIGN-1)) )>>1
            if r<=self.p.contents.pitchUV:return r
            else: return self.p.contents.row_size>>1
        elif plane==PLANAR_Y_ALIGNED:
            r=((self.p.contents.row_size+FRAME_ALIGN-1)&(~(FRAME_ALIGN-1)) )
            if r<=self.p.contents.pitch:return r
            else: return self.p.contents.row_size  
        return self.p.contents.pitch
    def GetHeight(self,plane=PLANAR_Y):
        if self.p.contents.pitchUV!=0 and (plane==PLANAR_U or plane==PLANAR_V):
            return self.p.contents.height/2
        return self.p.contents.height
    def GetReadPtr(self,plane=PLANAR_Y):
        if plane==PLANAR_Y:
            return ByRefAt(self.p.contents.AVS_VideoFrameBuffer.contents.data,
                           self.p.contents.offset)
        elif plane==PLANAR_U:
            return ByRefAt(self.p.contents.AVS_VideoFrameBuffer.contents.data,
                           self.p.contents.offsetU)
        elif plane==PLANAR_V:
            return ByRefAt(self.p.contents.AVS_VideoFrameBuffer.contents.data,
                           self.p.contents.offsetV)
        return ByRefAt(self.p.contents.AVS_VideoFrameBuffer.contents.data,
                       self.p.contents.offset)
    def IsWritable(self):
        return (self.p.contents.refcount==1 and \
                self.p.contents.AVS_VideoFrameBuffer.contents.refcount == 1)
    def GetWritePtr(self,plane=PLANAR_Y):
        if plane==PLANAR_Y and self.p.contents.IsWritable():
            self.p.contents.AVS_VideoFrameBuffer.contents.sequence_number = \
            self.p.contents.AVS_VideoFrameBuffer.contents.sequence_number+1
            return self.p.contents.AVS_VideoFrameBuffer.contents.data \
                   +self.p.contents.offset
        elif plane==PLANAR_Y:return 0
        elif plane==PLANAR_U:
            return ByRefAt(self.p.contents.AVS_VideoFrameBuffer.contents.data,
                           self.p.contents.offsetU)
        elif plane==PLANAR_V:
            return ByRefAt(self.p.contents.AVS_VideoFrameBuffer.contents.data,
                           self.p.contents.offsetV)
        return ByRefAt(self.p.contents.AVS_VideoFrameBuffer.contents.data,
                       self.p.contents.offset)
    def Copy(self):
        return avs_copy_video_frame(self)
    def Release(self):
        if self.p is not None:
            #print>>sys.stdout, "    Releasing PVideoFrame: ",self
            avs_release_video_frame(self.p)
        self.p=None
    def __del__(self):
        self.Release()
    def __call__( self,val):
        self.Release()
        self.p=val.Copy().p

        
class AVS_Value(ctypes.Structure,object):
    def __init__(self,val=None):
        self.type=ctypes.c_short(118)#='v'oid
        self.array_size=1
        self.d.f=0
        if val is not None:
            self.AssignVal(val)
    def AssignVal(self,val):
        # check 'bool' in front of 'int'      
        if isinstance(val,bool):self.SetBool(val)
        elif isinstance(val,int):self.SetInt(val)
        elif isinstance(val,float):self.SetFloat(val)
        elif isinstance(val,str):self.SetString(val)
        elif isinstance(val,unicode):self.SetString(val)
        elif isinstance(val,PClip):self.SetClip(val)
        elif isinstance(val,AVS_Value):val.Copy(self)
        elif isinstance(val,list):
            if isinstance(val[0],AVS_Value):self.SetArray(val)
    def __call__( self,val):
        self.AssignVal(val)
    def Release(self):
        avs_release_value(self)
        self.type=118
        self.array_size=1
        self.d.f=0
    def IsInt(self):return self.type==105
    def AsInt(self):
        if self.IsInt(): return self.d.i
        raise AvisynthError("Not an int")
    def IsString(self):return self.type==115
    def AsString(self):
        if self.IsString():return self.d.s
        raise AvisynthError("Not a string")
    def IsBool(self):return self.type==98
    def AsBool(self):
        if self.IsBool: return self.d.b
        raise AvisynthError("Not a bool")
    def IsClip(self):return self.type==99
    def AsClip(self,env):
        if self.IsClip(): return avs_take_clip(self,env)
        raise AvisynthError("Not a clip")
    def IsFloat(self):return self.type==102
    def AsFloat(self):
        if self.IsFloat():return self.d.f
        raise AvisynthError("Not a float")
    def IsArray(self):return self.type==97
    def IsError(self):return self.type==101
    def AsError(self):
        if self.IsError():return self.d.s
        raise AvisynthError("Not an error")
    def __getitem__( self, key):
        if self.IsArray():
            if array_size<key or key<0:
                raise IndexError 
            return AVS_Value(a[key])
        else:
            return self
    def SetInt(self,i):
        if self.type!=118:self.Release()
        self.type=105#='i'nt
        self.d.i=i
        self.array_size=1
    def SetString(self,s):
        if self.type!=118:self.Release()
        self.type=115#='s'tring
        self.d.s=s
        self.array_size=1
    def SetBool(self,b):
        if self.type!=118:self.Release()
        self.type=98#='b'ool
        self.d.b=b
        self.array_size=1        
    def SetClip(self,c):
        if self.type!=118:self.Release()
        avs_set_to_clip(ctypes.byref(self),c)
    def SetFloat(self,f):
        if self.type!=118:self.Release()
        self.type=102#='f'loat
        self.d.f=s
        self.array_size=1        
    def SetArray(self,a):
        if self.type!=118:self.Release()
        self.type=97#='a'rray
        self.array_size=len(a)
        if isinstance(a,list):
            AVS_VALUE_LIST=AVS_Value*len(a)
            aa=AVS_VALUE_LIST()
            for x in range(len(a)):
                aa[x]=a[x]
            a=ctypes.cast(ctypes.pointer(aa),ctypes.POINTER(AVS_Value))
        self.d.a=a
    def Copy(self,dst):
        avs_copy_value(ctypes.byref(dst),self)
    def __del__(self):
        self.Release()
        
class U(ctypes.Union):
       _fields_ = [("c",ctypes.c_void_p),
                   ("b",ctypes.c_long),
                   ("i",ctypes.c_int),
                   ("f",ctypes.c_float),
                   ("s",ctypes.c_char_p),
                   ("a",ctypes.POINTER(AVS_Value))]
           
AVS_Value._fields_ = [("type",ctypes.c_short),
                ("array_size",ctypes.c_short),
                ("d",U)]
    
class FilterInfo(ctypes.Structure):
    pass



GETFRAME=ctypes.WINFUNCTYPE(ctypes.POINTER(VideoFrame),
                            ctypes.POINTER(FilterInfo),ctypes.c_int)
GETPARITY=ctypes.WINFUNCTYPE(ctypes.c_int,ctypes.POINTER(FilterInfo),
                             ctypes.c_int)
GETAUDIO=ctypes.WINFUNCTYPE(ctypes.c_int,ctypes.POINTER(FilterInfo),
                            ctypes.c_void_p,ctypes.c_int64,ctypes.c_int64)
SETCACHEHINTS=ctypes.WINFUNCTYPE(ctypes.c_int,ctypes.POINTER(FilterInfo),
                                 ctypes.c_int,ctypes.c_int)
FREEFILTER=ctypes.WINFUNCTYPE(None,ctypes.POINTER(FilterInfo))

FilterInfo._fields_=[("child",ctypes.c_void_p),
                     ("vi",VideoInfo),
                     ("env",ctypes.c_void_p),
                     ("get_frame",GETFRAME),
                     ("get_parity",GETPARITY),
                     ("get_audio",GETAUDIO),
                     ("set_cache_hints",SETCACHEHINTS),
                     ("free_filter",FREEFILTER),
                     ("error",ctypes.c_char_p),
                     ("user_data",ctypes.c_void_p)]

def CreatePVideoFrameCT(result, func, arguments):return PVideoFrame(result)
def CreatePVideoInfoCT(result,func,arguments):return PVideoInfo(result)
def CreatePIScriptEnvironmentCT(result,func,arguments):return PIScriptEnvironment(result)


# Helper Fucntions
BI_RGB = 0

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize",  ctypes.c_ulong),
                ("biWidth",   ctypes.c_long),
                ("biHeight",   ctypes.c_long),
                ("biPlanes",   ctypes.c_ushort),
                ("biBitCount",   ctypes.c_ushort),
                ("biCompression",  ctypes.c_ulong),
                ("biSizeImage",  ctypes.c_ulong),
                ("biXPelsPerMeter",   ctypes.c_long),
                ("biYPelsPerMeter",   ctypes.c_long),
                ("biClrUsed",  ctypes.c_ulong),
                ("biClrImportant",  ctypes.c_ulong)]
    
def CreateBitmapInfoHeader(clip,bmih=None):
    vi=clip.GetVideoInfo()
    if bmih is None:
        bmih=BITMAPINFOHEADER()
    bmih.biSize=ctypes.sizeof(BITMAPINFOHEADER)
    bmih.biWidth=vi.width
    bmih.biHeight=vi.height
    bmih.biPlanes=1
    if vi.IsRGB32() is True:
        bmih.biBitCount=32
    elif vi.IsRGB24() is True:
        bmih.biBitCount=24
    else: raise AvisynthError("Input colorspace is not RGB24 or RGB32")
    bmih.biCompression=BI_RGB
    bmih.biSizeImage=vi.width*vi.height*bmih.biBitCount/8
    bmih.biXPelsPerMeter=0
    bmih.biYPelsPerMeter=0
    bmih.biClrUsed=0
    bmih.biClrImportant=0
    return bmih
    
    
    
        
#setup avisynth_c functions

#IScriptEnvironment functions
avs_create_script_environment=avidll.avs_create_script_environment 
avs_create_script_environment.restype = PIScriptEnvironment
avs_create_script_environment.argtypes= [ctypes.c_int]
PIScriptEnvironment.avs_create_script_environment=avs_create_script_environment
#avs_create_script_environment.errcheck=CreatePIScriptEnvironmentCT

avs_delete_script_environment=avidll.avs_delete_script_environment
avs_delete_script_environment.restype = None
avs_delete_script_environment.argtypes=[PIScriptEnvironment]

avs_get_cpu_flags=avidll.avs_get_cpu_flags
avs_get_cpu_flags.restype = ctypes.c_long
avs_get_cpu_flags.argtypes=[PIScriptEnvironment]

avs_check_version=avidll.avs_check_version
avs_check_version.restype = ctypes.c_int
avs_check_version.argtypes=[PIScriptEnvironment,ctypes.c_int]

avs_save_string=avidll.avs_save_string
avs_save_string.restype = ctypes.c_char_p
avs_save_string.argtypes=[PIScriptEnvironment,ctypes.c_char_p,ctypes.c_int]

avs_vsprintf=avidll.avs_sprintf
avs_vsprintf.restype = ctypes.c_char_p
avs_vsprintf.argtypes=[PIScriptEnvironment,ctypes.c_char_p,ctypes.c_void_p]

APPLYFUNC=ctypes.WINFUNCTYPE(ctypes.POINTER(AVS_Value),PIScriptEnvironment,
                             AVS_Value,ctypes.c_void_p)

avs_add_function=avidll.avs_add_function
avs_add_function.restype = ctypes.c_int
avs_add_function.argtypes=[PIScriptEnvironment,ctypes.c_char_p,ctypes.c_char_p,
                           APPLYFUNC,ctypes.c_void_p]

avs_function_exists=avidll.avs_function_exists
avs_function_exists.restype = ctypes.c_int
avs_function_exists.argtypes=[PIScriptEnvironment,ctypes.c_char_p]

avs_get_var=avidll.avs_get_var
avs_get_var.restype=AVS_Value
avs_get_var.argtypes=[PIScriptEnvironment,ctypes.c_char_p]

avs_set_var=avidll.avs_set_var
avs_set_var.restype=ctypes.c_int
avs_set_var.argtypes=[PIScriptEnvironment,ctypes.c_char_p,AVS_Value]

avs_set_global_var=avidll.avs_set_global_var
avs_set_global_var.restype=ctypes.c_int
avs_set_global_var.argtypes=[PIScriptEnvironment,ctypes.c_char_p,AVS_Value]

avs_new_video_frame_a=avidll.avs_new_video_frame_a
avs_new_video_frame_a.restype=ctypes.POINTER(VideoFrame)
avs_new_video_frame_a.argtypes=[PIScriptEnvironment,PVideoInfo,ctypes.c_int]
avs_new_video_frame_a.errcheck=CreatePVideoFrameCT

avs_make_writable=avidll.avs_make_writable
avs_make_writable.restype=ctypes.c_int
avs_make_writable.argtypes=[PIScriptEnvironment,
                            ctypes.POINTER(ctypes.POINTER(VideoFrame))]

avs_bit_blt=avidll.avs_bit_blt
avs_bit_blt.restype=None
avs_bit_blt.argtypes=[PIScriptEnvironment,ctypes.POINTER(ctypes.c_ubyte),
                      ctypes.c_int,ctypes.POINTER(ctypes.c_ubyte),
                      ctypes.c_int,ctypes.c_int,ctypes.c_int]

SHUTDOWNFUNC=ctypes.WINFUNCTYPE(ctypes.c_void_p,PIScriptEnvironment)

avs_at_exit=avidll.avs_at_exit
avs_at_exit.restype=None
avs_at_exit.argtypes=[PIScriptEnvironment,SHUTDOWNFUNC,ctypes.c_void_p]

avs_set_memory_max=avidll.avs_set_memory_max
avs_set_memory_max.restype=ctypes.c_int
avs_set_memory_max.argtypes=[PIScriptEnvironment,ctypes.c_int]

avs_set_working_dir=avidll.avs_set_working_dir
avs_set_working_dir.restype=ctypes.c_int
avs_set_working_dir.argtypes=[PIScriptEnvironment,ctypes.c_char_p]

avs_subframe_planar=avidll.avs_subframe_planar
avs_subframe_planar.restype=ctypes.POINTER(VideoFrame)
avs_subframe_planar.argtypes=[PIScriptEnvironment,PVideoFrame,ctypes.c_int,
                              ctypes.c_int,ctypes.c_int,ctypes.c_int,
                              ctypes.c_int,ctypes.c_int,ctypes.c_int]
avs_subframe_planar.errcheck=CreatePVideoFrameCT

avs_subframe=avidll.avs_subframe
avs_subframe.restype=ctypes.POINTER(VideoFrame)
avs_subframe.argtypes=[PIScriptEnvironment,PVideoFrame,ctypes.c_int,
                       ctypes.c_int,ctypes.c_int,ctypes.c_int]
avs_subframe.errcheck=CreatePVideoFrameCT

avs_invoke=avidll.avs_invoke
avs_invoke.restype=AVS_Value
avs_invoke.argtypes=[PIScriptEnvironment,ctypes.c_char_p,
                     AVS_Value,ctypes.POINTER(ctypes.c_char_p)]

#IClip functions
avs_take_clip=avidll.avs_take_clip
avs_take_clip.restype=PClip
avs_take_clip.argtypes=[AVS_Value,PIScriptEnvironment]

avs_set_to_clip=avidll.avs_set_to_clip
avs_set_to_clip.restype=None
avs_set_to_clip.argtypes=[ctypes.POINTER(AVS_Value),PClip]

avs_clip_get_error=avidll.avs_clip_get_error
avs_clip_get_error.restype=ctypes.c_char_p
avs_clip_get_error.argtypes=[PClip]

avs_get_video_info=avidll.avs_get_video_info
avs_get_video_info.restype=ctypes.POINTER(VideoInfo)
avs_get_video_info.argtypes=[PClip]
avs_get_video_info.errcheck=CreatePVideoInfoCT

avs_get_frame=avidll.avs_get_frame
avs_get_frame.restype=ctypes.POINTER(VideoFrame)
avs_get_frame.argtypes=[PClip,ctypes.c_int]
avs_get_frame.errcheck=CreatePVideoFrameCT

avs_get_version=avidll.avs_get_version
avs_get_version.restype=ctypes.c_int
avs_get_version.argtypes=[PClip]

avs_get_parity=avidll.avs_get_parity
avs_get_parity.restype=ctypes.c_int
avs_get_parity.argtypes=[PClip,ctypes.c_int]

avs_get_audio=avidll.avs_get_audio
avs_get_audio.restype=ctypes.c_int
avs_get_audio.argtypes=[PClip,ctypes.c_void_p,ctypes.c_int64,ctypes.c_int64]

avs_set_cache_hints=avidll.avs_set_cache_hints
avs_set_cache_hints.restype=ctypes.c_int
avs_set_cache_hints.argtypes=[PClip,ctypes.c_int,ctypes.c_int]

avs_copy_clip=avidll.avs_copy_clip
avs_copy_clip.restype=PClip
avs_copy_clip.argtypes=[PClip]

avs_release_clip=avidll.avs_release_clip
avs_release_clip.restype=None
avs_release_clip.argtypes=[ctypes.c_int]
PClip.avs_release_clip=avs_release_clip

avs_new_c_filter=avidll.avs_new_c_filter
avs_new_c_filter.restype=PClip
avs_new_c_filter.argtypes=[PIScriptEnvironment,
                           ctypes.POINTER(ctypes.POINTER(FilterInfo)),
                           AVS_Value,
                           ctypes.c_int]


#VideoFrame functions
avs_copy_video_frame=avidll.avs_copy_video_frame
avs_copy_video_frame.restype=ctypes.POINTER(VideoFrame)
avs_copy_video_frame.argtypes=[PVideoFrame]
avs_copy_video_frame.errcheck=CreatePVideoFrameCT

avs_release_video_frame=avidll.avs_release_video_frame
avs_release_video_frame.restype=None
avs_release_video_frame.argtypes=[ctypes.POINTER(VideoFrame)]

#AVS_Value functions
avs_copy_value=avidll.avs_copy_value
avs_copy_value.restype=None
avs_copy_value.argtypes=[ctypes.POINTER(AVS_Value),AVS_Value]

avs_release_value=avidll.avs_release_value
avs_release_value.restype=None
avs_release_value.argtypes=[AVS_Value]
AVS_Value.avs_release_value=avs_release_value


if __name__ == '__main__':
    def fx():
        print>>sys.stdout, "start"
        env=avs_create_script_environment(3)
        #print>>sys.stdout, "0"
        script="""
        a=5+7
        Version().ConvertToYV12()
        """
        #print>>sys.stdout, "1"
        iparm=AVS_Value("""import("e:\\t.avs")""")
        #print>>sys.stdout, "2"
        iparm(script)
        print>>sys.stdout, "Creating script:",script
        retval=env.Invoke("eval",iparm,0)
        clip=retval.AsClip(env)
        vi=clip.GetVideoInfo()
        print>>sys.stdout, "width: ",vi.width," height: ",vi.height,\
        " number of frames: ",vi.num_frames
        frame=clip.GetFrame(0)
        p=frame.GetReadPtr()
        print>>sys.stdout, "First 40 lumapixel: ",p[0:40]
        extfunc=env.GetVar("$PluginFunctions$")
        intfunc=env.GetVar("$InternalFunctions$")
        funclist=(extfunc.d.s+" "+intfunc.d.s).split(" ")
        extfunc=env.GetVar("a")
        print>>sys.stdout, "script variable a: ",extfunc.AsInt()
        extfunc.Release()
        intfunc.Release()
        #frame=0
        #clip=0


        def pton(x):
            if x=="c":
                return "clip"
            elif x=="i":
                return "int"
            elif x=="b":
                return "bool"
            elif x=="f":
                return "float"
            elif x=="s":
                return "string"
            elif x==".":
                return " [, ...]"
            elif x=="+":
                return " [, ...]"
            else:
                return "?"
        #print>>sys.stdout, "Printing funct list:"        
        for f in funclist:
            try:
                t=env.GetVar("$Plugin!"+f+"!Param$")
            except AvisynthError:
                break
            if t.d.c is not None:
                arglist="("
                namedarg=False
                namedargname=""
                for x in t.d.s:
                    if x=="[":
                        namedarg=True
                    elif x=="]":
                        namedarg=False
                    elif namedarg:
                        namedargname=namedargname+x
                    elif not namedarg:
                       if x=="." or x=="+" and arglist!="(":
                           arglist=arglist[0:len(arglist)-2]
                       arglist=arglist+pton(x)
                       if namedargname!="":
                           arglist=arglist+" "+namedargname
                           namedargname=""
                       arglist=arglist+", "
                arglist=arglist[0:len(arglist)-2]+")"
    #~ fx()
        #~ print>>sys.stdout, f+arglist
        #t.Release()

    #env.Release()
    
    
    env = avs_create_script_environment(3)
    
    #~ script=(
        #~ 'LoadPlugin("D:\Programs\AviSynth 2.5\Deen.dll")\n'
        #~ 'a=5+7\n'
        #~ 'Version().ConvertToYV12()\n'
    #~ )
    #~ iparm=AVS_Value('import("e:\\t.avs")')
    #~ iparm(script)
    #~ print>>sys.stdout, "Creating script:",script
    #~ retval=env.Invoke("eval",iparm,0)
    #~ clip=retval.AsClip(env)
    
    extfunc = avs_get_var(env,"$PluginFunctions$")
    intfunc = avs_get_var(env,"$InternalFunctions$")
    intfuncList = [(name, 0) for name in intfunc.d.s.split(' ')]
    extfuncList = [(name, 2) for name in extfunc.d.s.split(' ')]
    extfunc.Release()
    intfunc.Release()
    funclist = intfuncList + extfuncList
    typeDict = {
        'c': 'clip',
        'i': 'int',
        'f': 'float',
        'b': 'bool',
        's': 'string',
        '.': 'var',
        '*': '[...]',
    }
    functionDict = {}
    for name, functionType in funclist:
        if name.strip() == '':
            continue
        t = avs_get_var(env,"$Plugin!"+name+"!Param$")
        if t.d.c is not None:
            argList = []
            namedarg = False
            namedargname = []
            for i, c in enumerate(t.d.s):
                if c == '[':
                    namedarg = True
                elif c == ']':
                    namedarg = False
                elif namedarg:
                    namedargname.append(c)
                else:
                    namedargindex = len(argList)
                    if c == '+':
                        try:
                            typeDict[t.d.s[i-1]] # Helps ensure previous arg is valid
                            argList[-1] += ' [, ...]'
                        except (IndexError, KeyError):
                            print>>sys.stderr, (
                                'Error parsing %s plugin parameters: '
                                '+ without preceeding argument') % name
                    else:
                        try:
                            typeValue = typeDict[c]
                        except KeyError:
                            print>>sys.stderr, (
                                'Error parsing %s plugin parameters: '
                                'unknown character %s') % (name, c)
                            typeValue = '?'
                        argList.append(typeValue)
                    if namedargname:
                        try:
                            argList[namedargindex] += ' '+''.join(namedargname)
                        except IndexError:
                            print>>sys.stderr, (
                                'Error parsing %s plugin parameters: '
                                '[name] without following argument') % name
                            argList.append(''.join(namedargname))
                        namedargname = []
            argstring = '(%s)' % (', '.join(argList))
        t.Release()
        # Store the function info into the functionDict dictionary
        # The info consists of (arglist, preset, docpath, functionType)
        functionDict[name] = (argstring, '', '', functionType)
    env.Release()

    keys = [k for k,v in functionDict.items() if v[3] != 0 and v[0].count('*') > 0]
    keysdec = [(k.lower(), k) for k,v in functionDict.items() if v[3] != 0]
    keysdec.sort()
    for klower, k in keysdec:
        print k+functionDict[k][0]

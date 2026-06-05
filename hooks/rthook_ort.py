import ctypes
import os
import sys

if hasattr(sys, "_MEIPASS"):
    _ort = os.path.join(sys._MEIPASS, "onnxruntime.dll")
    if os.path.exists(_ort):
        ctypes.CDLL(_ort)

"""
Windows DPAPI (CryptProtectData / CryptUnprotectData) through ctypes, no extra packages.

Data sealed here can only be unsealed by the same Windows user account on the same PC
(Windows derives the key from the account's credentials). Sentinel uses it to bind the
PIN-wrapped data key to your Windows login.
"""
import ctypes
import sys

CRYPTPROTECT_UI_FORBIDDEN = 0x1


def available() -> bool:
    return sys.platform == "win32"


if available():
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
                                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                                            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    def _in_blob(data: bytes):
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def _take(out: "_Blob") -> bytes:
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))

    def protect(data: bytes, entropy: bytes = b"") -> bytes:
        inb, _k1 = _in_blob(data)
        ent, _k2 = _in_blob(entropy)
        out = _Blob()
        if not _crypt32.CryptProtectData(ctypes.byref(inb), "Sentinel", ctypes.byref(ent), None, None,
                                         CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            raise OSError(ctypes.get_last_error(), "CryptProtectData failed")
        return _take(out)

    def unprotect(blob: bytes, entropy: bytes = b"") -> bytes:
        inb, _k1 = _in_blob(blob)
        ent, _k2 = _in_blob(entropy)
        out = _Blob()
        if not _crypt32.CryptUnprotectData(ctypes.byref(inb), None, ctypes.byref(ent), None, None,
                                           CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            raise OSError(ctypes.get_last_error(), "CryptUnprotectData failed (other Windows user or PC?)")
        return _take(out)
else:
    def protect(data: bytes, entropy: bytes = b"") -> bytes:
        raise OSError("DPAPI is only available on Windows")

    def unprotect(blob: bytes, entropy: bytes = b"") -> bytes:
        raise OSError("DPAPI is only available on Windows")

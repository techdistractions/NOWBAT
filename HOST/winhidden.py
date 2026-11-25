"""Render DOSBox-X on an unshown Win32 desktop; never switch input desktop.

No post-launch hiding race, SDL dummy driver, or DOS-only -silent mode.
Failure to create the private desktop aborts launch instead of showing UI.
Uses the CreateDesktop/CreateProcess model of the current NOWBASIC
NOWN16/TESTS/PARITY/WINHIDE.PY, with checked 64-bit handle signatures.
"""
import ctypes as c
from ctypes import wintypes as w
import os
import subprocess
import uuid


class StartupInfo(c.Structure):
    _fields_ = [('cb', w.DWORD), ('lpReserved', w.LPWSTR),
                ('lpDesktop', w.LPWSTR), ('lpTitle', w.LPWSTR),
                ('dwX', w.DWORD), ('dwY', w.DWORD), ('dwXSize', w.DWORD),
                ('dwYSize', w.DWORD), ('dwXCountChars', w.DWORD),
                ('dwYCountChars', w.DWORD), ('dwFillAttribute', w.DWORD),
                ('dwFlags', w.DWORD), ('wShowWindow', w.WORD),
                ('cbReserved2', w.WORD), ('lpReserved2', c.POINTER(c.c_byte)),
                ('hStdInput', w.HANDLE), ('hStdOutput', w.HANDLE),
                ('hStdError', w.HANDLE)]


class ProcessInfo(c.Structure):
    _fields_ = [('hProcess', w.HANDLE), ('hThread', w.HANDLE),
                ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD)]


class HiddenProcess:
    def __init__(self, args, cwd, stream):
        if os.name != 'nt':
            raise OSError('Hidden native guest qualification requires Windows')
        import msvcrt
        self.args, self.returncode = args, None
        self.k = c.WinDLL('kernel32', use_last_error=True)
        self.u = c.WinDLL('user32', use_last_error=True)
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        self.k.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
        self.k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
        self.u.CreateDesktopW.argtypes = [w.LPCWSTR, w.LPCWSTR, c.c_void_p,
                                          w.DWORD, w.DWORD, c.c_void_p]
        self.u.CreateDesktopW.restype = w.HANDLE
        self.u.CloseDesktop.argtypes = [w.HANDLE]
        self.k.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, c.c_void_p,
            c.c_void_p, w.BOOL, w.DWORD, c.c_void_p, w.LPCWSTR,
            c.POINTER(StartupInfo), c.POINTER(ProcessInfo)]
        self.k.CreateProcessW.restype = w.BOOL
        self.desktop_name = 'WAS_' + uuid.uuid4().hex
        self.desktop = self.u.CreateDesktopW(self.desktop_name, None, None,
                                             0, 0x10000000, None)
        if not self.desktop:
            raise c.WinError(c.get_last_error())
        self.handle = None
        try:
            with open(os.devnull, 'rb') as stdin:
                output = msvcrt.get_osfhandle(stream.fileno())
                input_handle = msvcrt.get_osfhandle(stdin.fileno())
                previous = [os.get_handle_inheritable(h) for h in (input_handle, output)]
                try:
                    for h in (input_handle, output):
                        os.set_handle_inheritable(h, True)
                    si = StartupInfo()
                    si.cb = c.sizeof(si)
                    si.lpDesktop = self.desktop_name
                    si.dwFlags = 0x100 | 1  # USESTDHANDLES | USESHOWWINDOW
                    si.wShowWindow = 0
                    si.hStdInput, si.hStdOutput, si.hStdError = input_handle, output, output
                    pi = ProcessInfo()
                    command = c.create_unicode_buffer(subprocess.list2cmdline(args))
                    if not self.k.CreateProcessW(args[0], command, None, None, True,
                            0x08000000, None, str(cwd), c.byref(si), c.byref(pi)):
                        raise c.WinError(c.get_last_error())
                    self.handle, self.pid = pi.hProcess, pi.dwProcessId
                    self.k.CloseHandle(pi.hThread)
                finally:
                    for h, old in zip((input_handle, output), previous):
                        os.set_handle_inheritable(h, old)
        except BaseException:
            self.close()
            raise

    def poll(self):
        if self.returncode is None and self.k.WaitForSingleObject(self.handle, 0) == 0:
            code = w.DWORD()
            if not self.k.GetExitCodeProcess(self.handle, c.byref(code)):
                raise c.WinError(c.get_last_error())
            self.returncode = code.value
        return self.returncode

    def wait(self, timeout=None):
        ms = 0xffffffff if timeout is None else int(timeout * 1000)
        if self.k.WaitForSingleObject(self.handle, ms) == 0x102:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return self.poll()

    def terminate(self):
        if self.poll() is None and not self.k.TerminateProcess(self.handle, 1):
            raise c.WinError(c.get_last_error())

    kill = terminate

    def window_count(self):
        callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        self.u.EnumDesktopWindows.argtypes = [w.HANDLE, callback_type, w.LPARAM]
        count = []
        @callback_type
        def visit(hwnd, unused):
            count.append(hwnd)
            return True
        c.set_last_error(0)
        if not self.u.EnumDesktopWindows(self.desktop, visit, 0) and c.get_last_error():
            raise c.WinError(c.get_last_error())
        return len(count)

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None
        if self.desktop:
            if not self.u.CloseDesktop(self.desktop):
                raise c.WinError(c.get_last_error())
            self.desktop = None

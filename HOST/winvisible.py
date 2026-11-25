"""Launch DOSBox-X on the caller's visible desktop for interactive guest triage.

Unlike winhidden.HiddenProcess this deliberately does not create or select a
private Win32 desktop. Keep the same small process lifecycle API so native UAT
still enforces its timeout, checks natural exit, and packages failure evidence.
This module runs on the HOST only; it is never linked into Win16 WAS.EXE.
"""
import subprocess


class VisibleProcess:
    def __init__(self, args, cwd, stream):
        self.args = args
        self.desktop_name = None  # the interactive desktop, not a private one
        self.process = subprocess.Popen(
            args, cwd=str(cwd), stdin=subprocess.DEVNULL,
            stdout=stream, stderr=subprocess.STDOUT,
            close_fds=True,
        )
        self.pid = self.process.pid

    @property
    def returncode(self):
        return self.process.returncode

    def poll(self):
        return self.process.poll()

    def wait(self, timeout=None):
        return self.process.wait(timeout=timeout)

    def terminate(self):
        return self.process.terminate()

    def kill(self):
        return self.process.kill()

    def window_count(self):
        # The visible desktop belongs to the user, so counting its windows
        # would incorrectly include all their unrelated applications. The
        # emulator process must have exited before it can pass this check.
        return 0 if self.poll() is not None else 1

    def close(self):
        # No desktop handle was created. Release our remaining Popen handle
        # after wait/exit so Windows can close its process handle as well.
        if self.poll() is None:
            raise RuntimeError('Visible DOSBox-X process is still running')
        self.process = None

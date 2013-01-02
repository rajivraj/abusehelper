#!/usr/bin/env python

import os
import re
import sys
import pwd
import time
import errno
import signal
import platform

# Helpers

def get_effective_username():
    return pwd.getpwuid(os.getuid()).pw_name

def module_id(module):
    import hashlib

    return hashlib.sha1(module).hexdigest() + "-" + module

def popen(*args, **keys):
    import subprocess

    defaults = dict(stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE)
    defaults.update(keys)
    return subprocess.Popen(args, **defaults)

def send_signal(pid, signum):
    try:
        os.kill(pid, signum)
    except OSError, ose:
        if ose.errno != errno.ESRCH:
            raise

def ps():
    process = popen("ps", "-wweo", "pid=,ppid=,command=")
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        sys.stderr.write(stderr)
        sys.stderr.flush()
        sys.exit(process.returncode)

    found = list()
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid, ppid, command = line.split(None, 2)
        found.append((int(pid), int(ppid), command))
    return found

def find(module, processes=None):
    rex = re.compile(r"\s" + re.escape(module_id(module)))
    if processes is None:
        processes = ps()

    found = list()
    for pid, ppid, command in processes:
        if rex.search(command):
            found.append((int(pid), command))
    return found

def is_running(module):
    return not not find(module)

def _signal(module, signame, signum):
    waiting = set()

    try:
        while True:
            pids = find(module)
            if not pids:
                break

            for item in pids:
                if item in waiting:
                    continue
                pid, command = item

                send_signal(pid, signum)
                print "Sent %s to process %d." % (signame, pid)

            waiting = set(pids)
            time.sleep(0.2)
    finally:
        pids = find(module)
        if pids:
            print "Warning, some instances survived:"
            print "  pid=%d command=%r" % (pid, command)

def normalized_module(module):
    module = os.path.abspath(module)
    if os.path.isdir(module):
        module = os.path.join(module, "startup.py")
    return module

def logpath(module):
    path, filename = os.path.split(module)
    return os.path.join(path, "log", filename + ".log")

# Commands

def command_start(module):
    module = normalized_module(module)
    if is_running(module):
        print "Already running."
        return

    logfile = open(logpath(module), "a")
    try:
        print "Starting."
        process = popen(sys.executable,
                        "-m", "runpy",
                        "abusehelper.core.startup", module,
                        module_id(module),
                        stdout=logfile,
                        stderr=logfile,
                        close_fds=True)
    finally:
        logfile.close()

    for _ in xrange(20):
        retcode = process.poll()
        if retcode is not None:
            print "Warning, process died with return code %d" % retcode
            return
        time.sleep(0.1)

def command_status(module):
    module = normalized_module(module)

    processes = ps()
    pids = find(module, processes)
    if not pids:
        print "Not running."
        return

    if len(pids) == 1:
        print "1 instance running:"
    else:
        print "%d instances running:" % len(pids)

    parents = dict()
    for pid, ppid, command in processes:
        parents.setdefault(ppid, list()).append((pid, command))

    for parent_pid, parent_command in pids:
        print "[%d] %s" % (parent_pid, parent_command)

        for pid, command in parents.get(parent_pid, ()):
            print "  [%d] %s" % (pid, command)

def command_stop(module):
    module = normalized_module(module)
    if not is_running(module):
        print "Nothing running."
    else:
        print "Shutting down."
        _signal(module, "SIGUSR1", signal.SIGUSR1)

def command_kill(module):
    module = normalized_module(module)
    if not is_running(module):
        print "Nothing running."
    else:
        print "Shutting down."
        _signal(module, "SIGUSR2", signal.SIGUSR2)

def command_restart(module):
    module = normalized_module(module)
    command_stop(module)
    command_start(module)

def command_follow(module):
    module = normalized_module(module)
    height = 20
    try:
        process = popen("stty", "size", stdin=sys.stdin)
    except OSError:
        pass
    else:
        stdout, _ = process.communicate()
        if process.returncode == 0:
            try:
                height = max(int(stdout.split()[0])-2, 0)
            except ValueError:
                pass

    process = popen("tail", "-n", str(height), "-f", logpath(module),
                    stdout=sys.stdout,
                    stderr=sys.stderr)
    try:
        while is_running(module):
            time.sleep(0.2)
    finally:
        send_signal(process.pid, signal.SIGKILL)

def command_confgen(module):
    from abusehelper.contrib.confgen import confgen
    confgen.generate(module)

def main():
    from optparse import OptionParser

    parser = OptionParser(usage="usage: %prog [options] command module")
    parser.add_option("-p", "--python",
        dest="python",
        default=None,
        help="use the given python executable instead of %r" % sys.executable)
    parser.add_option("--allow-root",
        action="store_true",
        dest="allow_root",
        default=False,
        help="allow starting bots as the root user")
    options, args = parser.parse_args()

    if not options.allow_root and get_effective_username() == "root":
        parser.error("running as root - " +
            "run as a different user or specify the --allow-root " +
            "command line option")

    if options.python is not None:
        os.execlp(options.python, options.python, sys.argv[0], *args)
    if sys.version_info < (2, 6):
        parser.error("this tool requires python >= 2.6 " +
            "(you are running python %s), " % (platform.python_version()) +
            "use the option -p/--python to define a suitable python executable")

    if len(args) < 2:
        parser.error("expected command and module arguments")
    command, module = args

    command_func = globals().get("command_" + command.lower())
    if not callable(command_func):
        raise Exception("no command %r" % command)

    command_func(normalized_module(module))

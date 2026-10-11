"""Terminal activity bar for native builds without an invented completion percentage."""

import sys
import shutil
import threading
import time


class BuildProgress:
    def __init__(self, stream=None, *, interval=.25):
        self.stream = sys.stderr if stream is None else stream
        self.interval = interval
        self.tty = bool(self.stream.isatty())
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        self.started = None
        self.label = ''
        self.last_output = ''
        self.lines = 0
        self.frame = 0
        self.last_print = 0
        self.finished = False

    def __enter__(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        with self.lock:
            if self.tty and self.started is not None:
                self.stream.write('\r\033[2K')
                self.stream.flush()

    def message(self, message):
        with self.lock:
            if self.tty and self.started is not None:
                self.stream.write('\r\033[2K')
            self.stream.write(str(message) + '\n')
            self.stream.flush()

    def event(self, event):
        with self.lock:
            if self.started is None:
                self.started = time.monotonic()
            if event['kind'] == 'stage':
                self.label = event['message']
                self.last_output = ''
                self.lines = 0
                self.last_print = 0
            elif event['kind'] == 'output':
                self.lines += 1
                self.last_output = ''.join(c for c in event['message'] if c.isprintable())[-100:]
            elif event['kind'] == 'complete':
                self.finished = True
                if self.tty:
                    self.stream.write('\r\033[2K')
                self.stream.write('Native build verified.\n')
                self.stream.flush()

    def render(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if self.started is None or self.finished:
                return
            if not self.tty and now - self.last_print < 10:
                return
            elapsed = max(0, int(now - self.started))
            position = self.frame % 28
            position = position if position <= 14 else 28 - position
            bar = ' ' * position + '====' + ' ' * (14 - position)
            text = f'[{bar}] {self.label} | elapsed {elapsed//60:02}:{elapsed%60:02} | {self.lines} build messages'
            if self.last_output:
                text += ' | ' + self.last_output
            if self.tty:
                width = shutil.get_terminal_size(fallback=(100, 24)).columns
                text = text[:max(20, width - 1)]
                self.stream.write('\r\033[2K' + text)
            else:
                self.stream.write(text + '\n')
            self.stream.flush()
            self.frame += 1
            self.last_print = now

    def run(self):
        while not self.stop.wait(self.interval):
            self.render()

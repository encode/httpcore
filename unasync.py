#!venv/bin/python
import re
import os

SUBS = [
    ('AsyncIterator', 'Iterator'),
    ('Async([A-Z][A-Za-z_]*)', r'Sync\1'),
    ('async def', 'def'),
    ('await ', ''),
    ('__aenter__', '__enter__'),
    ('__aexit__', '__exit__'),
    ('__aiter__', '__iter__'),
]
COMPILED_SUBS = [
    (re.compile(r'\b' + regex + r'\b'), repl)
    for regex, repl in SUBS
]


def unasync_line(line):
    for regex, repl in COMPILED_SUBS:
        line = re.sub(regex, repl, line)
    return line


def unasync_file(in_path, out_path):
    with open(in_path, "r") as in_file:
        with open(out_path, "w") as out_file:
            for line in in_file.readlines():
                line = unasync_line(line)
                out_file.write(line)


def unasync_dir(in_dir, out_dir):
    for dirpath, dirnames, filenames in os.walk(in_dir):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            rel_dir = os.path.relpath(dirpath, in_dir)
            in_path = os.path.abspath(os.path.join(in_dir, rel_dir, filename))
            out_path = os.path.abspath(os.path.join(out_dir, rel_dir, filename))
            unasync_file(in_path, out_path)


def main():
    unasync_dir("httpcore/_async", "httpcore/_sync")


if __name__ == '__main__':
    main()

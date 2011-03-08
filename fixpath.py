import glob
import os
import sys

PKG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'packages')

def fix():
    zips = os.path.join(PKG_PATH, '*.zip')
    pkgs = glob.glob(zips) + [PKG_PATH]
    for path in pkgs:
        if path not in sys.path:
            sys.path.insert(0, path)

fix()

if __name__ == '__main__':
    print '\n'.join(sys.path)

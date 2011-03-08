import glob
import os
import sys

from google.appengine.dist import use_library

PKG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'packages')

def fix():
    use_library('django', '0.96')
    zips = os.path.join(PKG_PATH, '*.zip')
    pkgs = glob.glob(zips) + [PKG_PATH]
    for path in pkgs:
        if path not in sys.path:
            sys.path.insert(0, path)

fix()

if __name__ == '__main__':
    print '\n'.join(sys.path)

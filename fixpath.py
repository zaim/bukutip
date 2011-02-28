import sys, os

ROOT_PATH = os.path.dirname(__file__)
PACKAGES_PATH = os.path.join(ROOT_PATH, 'packages')
for pkg in ('jinja2.zip', 'pdfminer.zip', ''):
    sys.path.insert(0, os.path.join(PACKAGES_PATH, pkg))

import os
import urllib2
from collections import defaultdict
from decimal import Decimal
from StringIO import StringIO
from pdfminer.pdfparser import PDFDocument, PDFParser
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams, LTPage, LTContainer, LTChar


class InfoConverter(TextConverter):
    def __init__(self, *args, **kwargs):
        self.results = []
        TextConverter.__init__(self, *args, **kwargs)

    def end_page(self, page):
        assert not self.stack
        assert isinstance(self.cur_item, LTPage)
        self.cur_item.fixate()
        #self.cur_item.analyze(self.laparams)
        self.receive_layout(self.cur_item)
        self.pageno += 1

    def receive_layout(self, page):
        rows = []
        for item in page:
            item.debug = 1
            rows.append(item)
        self.results.append(rows)


class TabConverter(InfoConverter):
    def __init__(self, *args, **kwargs):
        self.word_margin = 3.425
        InfoConverter.__init__(self, *args, **kwargs)

    def receive_layout(self, page):
        lines = defaultdict(lambda : [])
        for child in page:
            if isinstance(child, LTChar):
                (x1,y1,x2,y2) = child.bbox
                char = child.get_text().encode(self.codec)
                line = lines[-y1]
                line.append((x1, x2, char))

        for y in sorted(lines.keys()):
            line  = lines[y]
            items = []
            curr  = ''
            for i, (x1, x2, char) in enumerate(line):
                if i == 0:
                    curr += char
                    continue
                prev   = line[i - 1]
                margin = x1 - prev[1]
                if margin > self.word_margin:
                    items.append(curr)
                    curr = char
                else:
                    curr += char
                if i == len(line) - 1:
                    items.append(curr)
            self.results.append(items)


def convert(pdf, pages=None, mapper=None, debug=False):
    res = PDFResourceManager()
    out = StringIO()
    lap = LAParams()

    Device = TabConverter
    if debug:
        Device = InfoConverter

    dev = Device(res, out, codec='utf-8', laparams=lap)
    inp = StringIO(pdf)
    pages = process_pdf(res, dev, inp, pagenums=pages)
    dev.close()
    inp.close()
    out.close()

    results = []
    if not callable(mapper):
        mapper = lambda v: v

    if dev.results:
        for item in dev.results:
            item = mapper(item)
            if not item: continue
            results.append(item)

    return (results, len(pages))

def process_pdf(rsrcmgr, device, fp, pagenums=None, maxpages=100, password=''):
    # Create a PDF parser object associated with the file object.
    parser = PDFParser(fp)
    # Create a PDF document object that stores the document structure.
    doc = PDFDocument()
    # Connect the parser and document objects.
    parser.set_document(doc)
    doc.set_parser(parser)
    # Supply the document password for initialization.
    # (If no password is set, give an empty string.)
    doc.initialize(password)
    # Check if the document allows text extraction. If not, abort.
    if not doc.is_extractable:
        raise PDFTextExtractionNotAllowed('Text extraction is not allowed: %r' % fp)
    # Create a PDF interpreter object.
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    # Process each page contained in the document.
    pages = dict(enumerate(doc.get_pages()))
    for num, page in pages.iteritems():
        if pagenums and (num not in pagenums):
            continue
        interpreter.process_page(page)
        if maxpages and maxpages <= num + 1:
            break
    return pages

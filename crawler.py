import re
import logging
import cron
import settings
from urlparse import urlsplit
from os.path import splitext, basename
from google.appengine.api.labs import taskqueue
from google.appengine.ext import webapp
from google.appengine.ext.deferred import deferred
from BeautifulSoup import BeautifulSoup, BeautifulStoneSoup
from models import Document, store_books
from zaim import pdf2text, utils
from zaim.titlecase import titlecase

RE_FLOAT  = re.compile(r'([0-9\.]+)$')
BOOKXCESS = 'http://www.bookxcess.com/'
PDF_PROCESS_PAGES = 2


def parse_mph_rss(document, headers, filename=None):
    """Parses the MPH bestsellers RSS feed.
    """
    rss   = BeautifulStoneSoup(document.contents)
    items = rss.findAll('item')
    books = []

    for item in items:
        book = {
            "title": item.find('title'),
            "isbn13": item.find('isbn'),
            "authors": item.find('author'),
            "description": item.find('description')
        }

        for field, element in book.items():
            if element and element.contents:
                value = element.contents[0]
                if isinstance(value, basestring):
                    value = value.strip()
                    if field == 'authors':
                        value = [value,]
                    elif not field == 'description':
                        value = utils.RE_NEWLINE.sub(' ', value)
                    book[field] = value
            else:
                book[field] = None

        book['mph_bestseller'] = True
        book['_links'] = []

        links = {
            "thumbnail": item.find('image'),
            "info": item.find('link'),
        }

        for field, element in links.items():
            if element and element.contents:
                url = element.contents[0]
                if isinstance(url, basestring):
                    book['_links'].append({
                        "name": field,
                        "url": url
                    })

        books.append(book)

    logging.info('parse_mph_rss: %d books found' % len(books))

    if books:
        store_books(books)


def parse_bookxcess_html(document, headers, filename=None):
    """Parses Bookxcess book listings page
    """
    soup    = BeautifulSoup(document.contents)
    links   = soup.findAll(['a', 'area'], href=True)
    parsers = {
        '.htm': parse_bookxcess_html,
        '.html': parse_bookxcess_html,
        '.pdf': parse_bookxcess_pdf
    }
    urls = {}

    for link in links:
        url = link['href'].strip()
        if not url.startswith('http://'):
            url = BOOKXCESS + url
        urlp = urlsplit(url)
        path = urlp.path.lower()
        args = {
            "filename": basename(path)
        }
        ext = splitext(path)[1]
        if ext in parsers:
            parser = parsers[ext]
            urls[url] = (parser, args)

    for url, (parser, args) in urls.items():
        task_name = 'download-%s' % Document.hash_url(url)
        logging.info('parse_bookxcess_html: downloading %s in task %s' % (url, task_name))
        try:
            deferred.defer(download_page, url, callback=parser, args=args,
                           _name=task_name, _queue='downloader')
        except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError):
            pass


def parse_bookxcess_pdf(document, headers, filename=None, pages=None, debug=False):
    """Parses Bookxcess PDF files
    """
    def _map(item):
        if len(item) != 4:
            return None
        if filename == 'fiction.pdf':
            author, title, price, isbn = item
        else:
            title, author, price, isbn = item
        author = author.title()
        title  = titlecase(title)
        try:
            price = float(price)
        except ValueError:
            return None
        else:
            return {
                "isbn13": isbn,
                "title": title,
                "authors": [author],
                "_prices": [{
                    "source": 'bookxcess',
                    "price": price
                }]
            }

    if not pages:
        pages = range(0, PDF_PROCESS_PAGES)

    result, total = pdf2text.convert(document.contents, pages=pages, mapper=_map)
    logging.info('parse_bookxcess_pdf: %s: pages %s of %d: %d books found' % (filename, pages, total, len(result)))

    if debug:
        return result

    if result:
        store_books(result)

    if total > 1:
        next = pages[-1] + 1
        stop = next + PDF_PROCESS_PAGES
        next_pages = range(next, stop)
        if next < total:
            task_name = 'parse-bookxcess-pdf-%s-%s' % (document.urlhash, '-'.join([str(d) for d in next_pages]))
            logging.info('parse_bookxcess_pdf: next: %s' % task_name)
            try:
                deferred.defer(parse_bookxcess_pdf, document, headers,
                               filename, next_pages, _name=task_name)
            except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError):
                pass


def download_page(url, headers=None, callback=None, args=None):
    """Downloads a URL and optionally calls a callback function when done
    """
    headers = headers or {}
    user_agent = getattr(settings, 'USER_AGENT')
    if user_agent:
        headers['user-agent'] = user_agent
    document, info = Document.download(url, headers=headers, getinfo=True)
    if document and callable(callback):
        args = args or {}
        callback(document, info, **args)
    return (document, info)


class BookSourceTaskHandler(webapp.RequestHandler):
    def get(self):
        self.response.headers['content-type'] = 'text/plain'

        if self.request.get('dbg'):
            self.debug()
        else:
            source = self.request.get('source')
            name = self.request.get('name')
            urls, call = None, None

            callbacks = {
                'mph_rss': parse_mph_rss,
                'bookxcess_pdf': parse_bookxcess_pdf
            }

            TASKS = dict(cron.tasks)

            if source in TASKS:
                urlset = dict(TASKS[source]['urls'])
                if name in urlset:
                    urls = urlset[name]
                    call = TASKS[source]['callback']
                    call = callbacks.get(call, None)

            if urls and call:
                for url in urls:
                    urlp = urlsplit(url)
                    path = urlp.path.lower()
                    args = {
                        "_queue": 'downloader',
                        "_name": 'download-%s' % Document.hash_url(url),
                        "callback": call,
                        "args": {
                            "filename": basename(path)
                        }
                    }
                    self.response.out.write("%s\n" % url)
                    try:
                        deferred.defer(download_page, url, **args)
                    except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError):
                        pass
            else:
                self.error(500)
                self.response.out.write('No URLs or callback found: %s, %s' % (urls, call))

    def debug(self):
        show = self.request.get('show', 'results')
        meth = getattr(self, 'debug_%s' % show, None)
        if callable(meth):
            meth()
        else:
            self.response.write("Don't know what to show: %s" % show)

    def debug_results(self):
        name = self.request.get('name', 'chd')
        test_url = 'http://www.bookxcess.com/%s.pdf' % name
        document, info = download_page(test_url)
        if document:
            from pprint import pprint
            results = parse_bookxcess_pdf(document, info, filename='%s.pdf' % name, pages=[0], debug=True)
            pprint({"results":results, "info":info}, stream=self.response.out)
        else:
            self.response.out.write('document not available')

    def debug_cron(self):
        self.response.out.write(cron.generate_yaml())

"""Find book prices in various book shop websites"""

import re
import urllib
import urllib2
from datetime import datetime
from google.appengine.api import urlfetch
from BeautifulSoup import SoupStrainer, BeautifulSoup, BeautifulStoneSoup

RE_RM  = re.compile(r'^\s*(?P<currency>RM|MYR).*')
RE_RMV = re.compile(r'^\s*(?P<currency>RM|MYR)\s*(?P<price>[0-9\.]+)')

# the global bookshop registry
SHOPS = {}

def shop(url, **kwargs):
    """Decorates a function to become a web-based bookshop price parser.
    """
    def _wrapper(fn):
        name = fn.__name__
        SHOPS[name] = {
            "fn": fn,
            "url": url,
            "title": kwargs.get('title', name.capitalize()),
            "timeout": kwargs.get('timeout', 5)
        }
        return fn
    return _wrapper

def scrape(content, tag, attrs, text_match=RE_RM, price_parse=RE_RMV):
    strainer = SoupStrainer(tag, attrs)
    soup = BeautifulSoup(content, parseOnlyThese=strainer)
    price = soup.find(text=text_match)
    if price:
        match = price_parse.match(price.string)
        try:
            price = match.group('price')
            return float(price)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Price text mangled")
    else:
        raise ValueError("Price text not found")

@shop('http://www.mphonline.com/books/nsearch.aspx?do=detail&pcode=%(isbn13)s', timeout=10)
def mph(content, book, debug=False):
    return [
        {"price": scrape(content, 'td', {"class":'bookdesc'})}
    ]

@shop('http://www.timesbookstores.com.my/ProductDetail.aspx?item_code=%(isbn13)s', title='Times Bookstores')
def times(content, book, debug=False):
    return [
        {"price": scrape(content, 'span', {"id":'ctl00_maincontent_lblPrice', "class":'text_price'})}
    ]

@shop('http://bookweb.kinokuniya.co.jp/guest/cgi-bin/bookseaohb.cgi?ISBN=%(isbn13)s&AREA=05')
def kinokuniya(content, book, debug=False):
    return [
        {"price": scrape(content, 'font', {"color":'red'})}
    ]

# callable passed as shop's url to make the url dynamic
def mudah_url(book):
    title = book.get('title')
    authors = book.get('authors')
    if not title:
        raise ValueError("Mudah.my price finder requires book title")
    query = '"%s" %s' % (title, ' '.join([('"%s"' % a) for a in authors if a.strip()]))
    query = urllib.quote_plus(query.strip())
    # mudah.my/li search parameters:
    # ca = 9_s   ???
    # cg = 5060  category music/movies/books
    # w  = 3     location entire malaysia
    # sp = 1     sort by cheapest price
    # q  = %s    the search query
    return 'http://www.mudah.my/li?ca=9_s&cg=5060&w=3&sp=1&q=%s' % query

@shop(mudah_url, title='Mudah.my')
def mudah(content, book, debug=False):
    strainer = SoupStrainer('table', {"id":'hl'})
    soup = BeautifulSoup(content, parseOnlyThese=strainer)
    prices = []

    for row in soup('tr', {"class":lambda c: not c=='google_listing_ad'}):
        date, url, price = datetime.today(), None, None

        # get item url and price
        tds = row.findAll('td', {"nowrap":'nowrap'})
        if len(tds) > 1:
            item_td = tds[0]
            for e in item_td:
                if isinstance(e, unicode):
                    match = RE_RMV.match(e.strip())
                    if match:
                        price = float(match.group('price'))
                elif e.name == 'a':
                    url = e['href']

        # no need to proceed if url and price not found
        if url is None or price is None:
            continue

        # get post date
        date_th = row.find('th', {"class":'listing_thumbs_date'})
        if date_th:
            date_str = date_th.contents[0].strip().lower()
            try:
                date = datetime.strptime(date_str, '%d %b')
                date = date.replace(year=datetime.today().year)
            except ValueError, e:
                pass

        prices.append({
            "state": 1,
            "price": price,
            "url": url,
            "posted": date.date()
        })

    return prices

# pass None as url so that no content is downloaded. bookxcess finder directly
# find books from datastore, which are already populated during bookxcess pdf
# crawling cron tasks
@shop(None)
def bookxcess(book):
    obj = Book.get_by_isbn(book['isbn13'], defaults=book)
    prices = Price.find_for_book(obj, 'bookxcess')
    if prices:
        return prices
    else:
        return []

def find(name, book, debug=False):
    """The main price finder function.

    The `book` parameter is a dict matching fields with the `models.Book`
    entity. Returns a list of price dicts matching `models.Price` or actual
    entity objects.
    """
    shop = SHOPS.get(name)
    if shop is None:
        raise NameError("Shop '%s' not registered" % name)

    args = (book,)
    url = None

    if shop['url']:
        if callable(shop['url']):
            url = shop['url'](book)
        else:
            url = shop['url'] % book
        source = urlfetch.fetch(url, deadline=shop['timeout']).content
        args = (source, book)

    if debug:
        args = args + (True,)

    prices = shop['fn'](*args)

    for p in prices:
        if isinstance(p, dict):
            p['source'] = name
            if not p.get('url') and url:
                p['url'] = url

    return prices

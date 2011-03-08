"""Uses Google Book Search to search and optionally store books"""

import hashlib
import re
import urllib
import urllib2
import settings
import simplejson as json
from collections import defaultdict
from datetime import datetime
from google.appengine.api import memcache
from amazon import Amazon
from BeautifulSoup import BeautifulStoneSoup


GOOGLE_BOOKS_URL = 'http://books.google.com/books/feeds/volumes?q=%s&alt=json'

GOOGLE_BOOKS_LINKS = {
    "http://schemas.google.com/books/2008/info": 'info',
    "http://schemas.google.com/books/2008/preview": 'preview',
    "http://schemas.google.com/books/2008/thumbnail": 'thumbnail'
}

SEARCH_CACHE_TTL = 43200  # 12 hours


def gd_text(item, single=False, force_list=False):
    if isinstance(item, list):
        if single:
            if len(item): return gd_text(item[0])
            else: return u''
        else:
            return [gd_text(i) for i in item]
    elif isinstance(item, dict):
        if '$t' in item:
            if force_list:
                return [item['$t']]
            return item['$t']
    if force_list: return []
    else: return u''

def gd_ident(item):
    item = gd_text(item)
    res  = {
        "google": u'',
        "isbn10": u'',
        "isbn13": u''
    }
    for id in item:
        id = id.strip()
        if id.startswith('ISBN:'):
            num = id[5:]
            if len(num) == 10:
                res['isbn10'] = num
            elif len(num) == 13:
                res['isbn13'] = num
        else:
            res['google'] = id
    return res

def gd_transform(entry):
    ids = gd_ident(entry.get('dc$identifier'))
    book = {
        "google_id": ids['google'],
        "isbn13": ids['isbn13'],
        "isbn10": ids['isbn10'],
        "title": gd_text(entry.get('dc$title'), single=True),
        "authors": gd_text(entry.get('dc$creator'), force_list=True),
        "publishers": gd_text(entry.get('dc$publisher'), force_list=True),
        "description": gd_text(entry.get('dc$description'), single=True),
        "_links": []
    }

    date = gd_text(entry.get('dc$date'), single=True).strip()
    if date:
        try:
            if len(date) == 4:
                date = datetime.strptime(date, '%Y')
            elif len(date) == 10:
                date = datetime.strptime(date, '%Y-%m-%d')
            else:
                raise ValueError
        except ValueError:
            date = None
        else:
            date = date.date()
        book['published_date'] = date

    rating = entry.get('gd$rating', {}).get('average', 0)
    rating = int(float(rating) * 20)
    book['rating'] = rating

    for link in entry.get('link', []):
        rel = link.get('rel')
        if rel in GOOGLE_BOOKS_LINKS:
            name = GOOGLE_BOOKS_LINKS[rel]
            href = link.get('href')
            book['_links'].append({"name":name, "url":href})
    return book

def hash_query(query):
    query = re.sub(r'\s+', ' ', query).strip()
    return hashlib.sha1(query).hexdigest()

def search(query, hashed=None):
    query  = query.strip()
    memkey = 'search:%s' % (hashed if hashed else hash_query(query))
    cached = memcache.get(memkey)
    if cached:
        return cached

    books = google(query)
    isbns = dict([(b['isbn13'], b) for b in books if b.get('isbn13')])

    amazo = amazon(isbns.keys())
    for a in amazo:
        if not a['isbn13'] in isbns:
            continue
        b = isbns[a['isbn13']]
        for key in a.iterkeys():
            if key == '_prices' or key == '_links':
                items = b.get(key, [])
                items.extend(a[key])
                b[key] = items
            else:
                b[key] = a[key]

    results = isbns.values()
    memcache.set(memkey, results, SEARCH_CACHE_TTL)
    return results

def google(query):
    query = query.strip()
    if not query: return []

    url   = GOOGLE_BOOKS_URL % urllib.quote_plus(query)
    req   = urllib2.Request(url)
    src   = urllib2.urlopen(req)
    res   = json.loads(src.read())
    books = []

    if 'feed' in res and 'entry' in res['feed'] and res['feed']['entry']:
        for entry in res['feed']['entry']:
            book = gd_transform(entry)
            books.append(book)

    return books

def amazon(isbns):
    if isinstance(isbns, basestring):
        isbns = [isbns]
    isbns = isbns[:10]

    markup = amazon_lookup(isbns)
    soup = BeautifulStoneSoup(markup)
    items = soup.findAll('item')
    books = []

    if not items:
        return books

    for item in items:
        book = {
            "isbn13": ('ean', u''),
            "isbn10": ('isbn', u''),
            "amazon_id": ('asin', u''),
            "amazon_salesrank": ('salesrank', -1),
            "amazon_url": ('detailpageurl', u'')
        }

        for field, elename in book.items():
            name, default = elename
            elem = item.find(name)
            if elem and hasattr(elem, 'string'):
                value = unicode(elem.string)
                if field == 'amazon_salesrank':
                    value = int(value)
                book[field] = value
            else:
                book[field] = default

        book['_links']  = [
            {"name":'amazon', "url":book['amazon_url']}
        ]
        del book['amazon_url']

        #book['_prices'] = []
        #offers = item.find('offersummary')
        #for s, sname in enumerate(('new', 'used')):
        #    n = 'lowest%sprice' % sname
        #    e = offers.find(n)
        #    if e:
        #        p = {"state":s, "source":'amazon'}
        #        amount_el = e.find('amount')
        #        currency_el = e.find('currencycode')
        #        if amount_el:
        #            p['price'] = float(amount_el.string) / 100
        #        if currency_el:
        #            p['currency'] = unicode(currency_el.string)
        #        book['_prices'].append(p)

        books.append(book)

    return books

def amazon_lookup(isbns):
    ids = ','.join(isbns)
    amazon = Amazon(settings.AMAZON_KEY, settings.AMAZON_SECRET, settings.AMAZON_ASSOC)
    return amazon.ItemLookup(ItemId=ids, ResponseGroup='ItemAttributes,OfferSummary,SalesRank',
                             SearchIndex='Books', IdType='EAN')

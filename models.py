import logging
import re
import urllib2
import urlparse
import time
import booksearch
import settings
from cgi import parse_qsl
from collections import defaultdict
from datetime import datetime
from email.utils import formatdate
from hashlib import sha1
from google.appengine.api import memcache, urlfetch
from google.appengine.ext import db
from google.appengine.ext.deferred import deferred
from zaim import urlnorm


class NormalizedLinkProperty(db.LinkProperty):
    def validate(self, value):
        value = super(NormalizedLinkProperty, self).validate(value)
        if value is not None:
            # urltuple = scheme, netloc, path, query, fragment
            urltuple = urlparse.urlparse(value)
            if not urltuple.scheme or not urltuple.netloc:
                raise BadValueError('Property %s must be a full URL (\'%s\')' %
                                    (self.name, value))
            else:
                urltuple = urlnorm.norm(urltuple)
                value = urlparse.urlunparse(urltuple)
        return value


class Book(db.Model):
    MEMCACHE_TTL = 604800  # 7 days
    ISBN13_REGEX = re.compile(r'^([0-9]{13})$')
    ISBN10_REGEX = re.compile(r'^([0-9]{10})$')

    isbn13 = db.StringProperty(required=True)
    isbn10 = db.StringProperty()
    title = db.StringProperty()
    authors = db.StringListProperty()
    publishers = db.StringListProperty()
    published_date = db.DateProperty()
    rating = db.RatingProperty()
    description = db.StringProperty(multiline=True)
    google_id = db.StringProperty()
    amazon_id = db.StringProperty()
    amazon_salesrank = db.IntegerProperty()
    mph_bestseller = db.BooleanProperty()

    def __init__(self, *args, **kwargs):
        # automatically generate key_name
        if 'isbn13' in kwargs and kwargs['isbn13']:
            isbn = kwargs['isbn13']
            kwargs['key_name'] = 'book:%s' % isbn
        super(Book, self).__init__(*args, **kwargs)
        self.links = LinkAttribute(self)

    def __cmp__(self, other):
        if not self or not other:
            return -1
        return cmp(self.isbn13, other.isbn13)

    def __hash__(self):
        return hash(self.isbn13)

    def put(self):
        memcache.delete(self.memkey)
        return super(Book, self).put()

    def delete(self):
        memcache.delete(self.memkey)
        return super(Book, self).delete()

    @property
    def memkey(self):
        return 'book:%s' % self.isbn13

    @property
    def permalink(self):
        return '/%s' % self.isbn13

    @property
    def outlink(self):
        if 'amazon' in self.links:
            return self.links['amazon']
        elif 'info' in self.links:
            return self.links['info']
        else:
            return self.permalink

    @classmethod
    def get_by_isbn(cls, isbn, create=True, defaults=None):
        if not Book.ISBN13_REGEX.match(isbn):
            raise ValueError('Illegal ISBN value: %s' % isbn)

        memkey = 'book:%s' % isbn
        book = memcache.get(memkey)
        if book:
            return book

        if not create:
            book = Book.get_by_key_name(memkey)
        else:
            defaults = defaults or {}
            defaults['isbn13'] = isbn
            book = Book.get_or_insert(memkey, **defaults)

        if book:
            memcache.set(book.memkey, book, Book.MEMCACHE_TTL)
        return book


class Link(db.Model):
    name = db.StringProperty()
    book = db.ReferenceProperty(Book, required=True)
    url = NormalizedLinkProperty(required=True)

    def __init__(self, *args, **kwargs):
        self._urlhash = ''
        name = kwargs.get('name', 'default')
        book = kwargs.get('book')
        isbn = None
        if book:
            if isinstance(book, Book):
                isbn = book.isbn13
            elif isinstance(book, db.Key):
                isbn = book.name().split(':')[1]
            if isbn:
                kwargs['key_name'] = 'link:%s:%s' % (isbn, name)
        super(Link, self).__init__(*args, **kwargs)

    @property
    def urlhash(self):
        if not self._urlhash:
            self._urlhash = Document.hash(self.url)
        return self._urlhash


class LinkAttribute(object):
    def __init__(self, book):
        self._links_dict = None
        self._book = book

    @property
    def _links(self):
        if not self._links_dict:
            self._load()
        return self._links_dict

    def _load(self, max=64):
        self._links_dict = {}
        for ln in self._book.link_set.fetch(max):
            if not ln.url: continue
            self._links_dict[ln.name] = ln.url

    def __len__(self):
        return len(self._links)

    def __getitem__(self, name):
        return self._links[name]

    def __iter__(self):
        return self._links.iteritems()

    def __contains__(self, name):
        return (name in self._links)


class Price(db.Model):
    MEMCACHE_TTL = 86400  # 1 day

    book = db.ReferenceProperty(Book, required=True)
    source = db.StringProperty()
    state = db.IntegerProperty(default=0)
    price = db.FloatProperty()
    currency = db.StringProperty()
    posted = db.DateProperty()
    url = NormalizedLinkProperty()

    def put(self):
        memcache.delete('prices:%s:%s' % (self.book.isbn13, source))
        return super(Price, self).put()

    def delete(self):
        memcache.delete('prices:%s:%s' % (self.book.isbn13, source))
        return super(Book, self).delete()

    @classmethod
    def find_for_book(cls, book, source):
        # from memcache
        memkey = 'prices:%s:%s' % (book.isbn13, source)
        prices = memcache.get(memkey)
        if prices:
            return prices

        # from db
        query = Price.all()
        query.filter('book =', book)
        query.filter('source =', source)
        prices = query.fetch(100)

        if prices:
            memcache.set(memkey, prices, Price.MEMCACHE_TTL)
            return prices

        # from nothing :(
        return []


class Document(db.Model):
    MEMCACHE_TTL = 86400  # 1 day

    url = NormalizedLinkProperty(required=True)
    etag = db.StringProperty()
    last_updated = db.DateTimeProperty()
    contents = db.BlobProperty()

    def __init__(self, *args, **kwargs):
        self._urlhash = ''
        # automatically generate key_name
        if 'url' in kwargs and kwargs['url']:
            kwargs['url'] = urlnorm.norms(kwargs['url'])
            self._urlhash = Document.hash(kwargs['url'])
            kwargs['key_name'] = 'document:%s' % self._urlhash
        super(Document, self).__init__(*args, **kwargs)

    def __cmp__(self, other):
        if not self or not other:
            return -1
        return cmp(self.urlhash, other.urlhash)

    def __hash__(self):
        return hash(self.urlhash)

    def put(self):
        memcache.delete(self.memkey)
        return super(Document, self).put()

    def delete(self):
        memcache.delete(self.memkey)
        return super(Document, self).delete()

    def last_updated_format(self):
        ts = time.mktime(self.last_updated.timetuple())
        return formatdate(ts, usegmt=True)

    @property
    def urlhash(self):
        if not self._urlhash:
            self._urlhash = Document.hash(self.url)
        return self._urlhash

    @property
    def memkey(self):
        return 'document:%s' % self.urlhash

    @classmethod
    def download(cls, url, headers=None, getinfo=False):
        doc = Document.get_by_url(url)

        headers = headers or {}
        if doc.last_updated:
            headers['If-Modified-Since'] = doc.last_updated_format()
        if doc.etag:
            headers['ETag'] = doc.etag

        #try:
        #    resp = utils.download(url, headers=headers)
        #except urllib2.HTTPError, e:
        #    if e.code == 304:  # not modified
        #        resp = e
        #        mod  = False
        #    else: raise
        #
        #if resp:
        #    info = dict(resp.info().items())
        #    if mod:
        #        doc.contents = resp.read()
        #        doc.last_updated = datetime.utcnow()

        resp = urlfetch.fetch(url, headers=headers)
        if resp.status_code == 200:
            doc.contents = resp.content
            doc.last_updated = datetime.utcnow()

        doc.put()
        memcache.set(doc.memkey, doc, Document.MEMCACHE_TTL)

        if getinfo:
            return (doc, resp.headers)
        else:
            return (doc)

    @classmethod
    def get_by_url(cls, url, create=True):
        key = 'document:%s' % Document.hash_url(url)

        doc = memcache.get(key)
        if doc:
            return doc

        if not create:
            doc = Document.get_by_key_name(key)
        else:
            doc = Document.get_or_insert(key, url=url)

        if doc:
            memcache.set(key, doc, Document.MEMCACHE_TTL)
        return doc

    @classmethod
    def hash(cls, s):
        return sha1(s).hexdigest()

    @classmethod
    def hash_url(cls, url):
        url = urlnorm.norms(url)
        return Document.hash(url)


##### Utility Functions #####

def from_dict(Model, data):
    props = Model.properties()
    obj = {}
    for key, value in data.iteritems():
        if key in props:
            try:
                value = props[key].validate(value)
            except db.BadValueError:
                # immediately fail and return None when invalid
                return None
            obj[key] = value
    return obj

def store_books(books, update=False):
    """Checks for book duplicates and update or create new books accordingly
    """
    prices  = []
    links   = []

    # drop invalid books
    books = [b for b in books if b.get('isbn13')]

    # get existing books
    keys = [db.Key.from_path('Book', 'book:%s' % b['isbn13']) for b in books]
    objects = dict([(b.isbn13, b) for b in [o for o in db.get(keys)] if b])
    tostore = []

    for book in books:
        cur_prices = book.get('_prices', [])
        cur_links = book.get('_links',  [])
        cur_book = from_dict(Book, book)

        # truncate description
        descr = cur_book.get('description', '')
        if len(descr) > 500:
            cur_book['description'] = descr[0:500]

        # get existing object
        obj = objects.get(cur_book['isbn13'])
        if obj:
            # book already exist, update or not?
            if update:
                for k, v in cur_book.iteritems():
                    setattr(obj, k, v)
                tostore.append(obj)
        else:
            # book does not exist, create it
            obj = Book(**cur_book)
            tostore.append(obj)

        objects[obj.isbn13] = obj

        # add reference to book obj in prices/links
        for p in cur_prices: p['book'] = obj
        for l in cur_links:  l['book'] = obj
        prices.extend(cur_prices)
        links.extend(cur_links)

    if tostore:
        db.put(tostore)

    if objects:
        # invalidate an re-cache
        cache = dict([(b.memkey, b) for b in objects.values()])
        memcache.set_multi(cache, Book.MEMCACHE_TTL)

    if prices: store_prices(prices, update)
    if links:  store_links(links, update)

    return objects.values()

def store_prices(prices, update=False):
    """Checks for price duplicates and update or create prices accordingly
    """
    objects = []
    tostore = []
    books   = []

    # drop invalid prices
    prices = [p for p in prices if (p.get('book') and p.get('source'))]

    for price in prices:
        cur_price = from_dict(Price, price)

        # get by unique keys
        keys  = ['book', 'source', ('state', 0), 'posted']
        query = Price.all()
        for k in keys:
            k, v = k if isinstance(k, tuple) else (k, None)
            query.filter('%s = ' % k, cur_price.get(k, v))

        obj = query.get()

        if obj:
            # object exists, update?
            if update:
                for k, v in cur_price.iteritems():
                    setattr(obj, k, v)
                tostore.append(obj)
        else:
            # new object
            obj = Price(**cur_price)
            tostore.append(obj)

        objects.append(obj)
        books.append(cur_price['book'])

    if tostore:
        db.put(tostore)

    if objects:
        db.put(objects)
        deferred.defer(recache_book_prices, books)

    return objects

def recache_book_prices(books):
    """Re-caches book price objects
    """
    keys = defaultdict(lambda : [])
    for book in books:
        prices = book.price_set.fetch(200)
        for price in prices:
            key = 'prices:%s:%s' % (book.isbn13, price.source)
            keys[key].append(price)
    memcache.set_multi(keys, Price.MEMCACHE_TTL)

def store_links(links, update=False):
    """Checks for link duplicates and update or create links accordingly
    """
    # drop invalid links
    links = [ln for ln in links if (ln.get('book') and ln.get('name'))]

    # get existing ones
    names = ['link:%s:%s' % (ln['book'].isbn13, ln['name']) for ln in links]
    keys = [db.Key.from_path('Link', kn) for kn in names]
    objects = dict( [(o.key().name(), o) for o in db.get(keys) if o] )
    tostore = []

    for link in links:
        cur_link = from_dict(Link, link)

        #query = Link.all()
        #query.filter('book =', cur_link['book'])
        #query.filter('name =', cur_link['name'])

        key = 'link:%s:%s' % (cur_link['book'].isbn13, cur_link['name'])
        obj = objects.get(key)
        if obj:
            if update:
                for k, v in cur_link.iteritems():
                    setattr(obj, k, v)
                tostore.append(obj)
        else:
            obj = Link(**cur_link)
            tostore.append(obj)

        objects[key] = obj

    if tostore:
        db.put(tostore)

    return objects.values()

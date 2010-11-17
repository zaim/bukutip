import logging
import booksearch
import bookshop
import crawler
import settings
import pyisbn
import models
from collections import defaultdict
from google.appengine.api import memcache, mail, users
from google.appengine.ext import webapp, ereporter
from google.appengine.ext.webapp import util
from crawler import BookSourceTaskHandler
from zaim import utils, handlers

ereporter.register_logger()

def set_context(context):
    context.update({
        "user": users.get_current_user(),
        "login_url": users.create_login_url('/', None, 'gmail.com'),
        "logout_url": users.create_logout_url('/')
    })

handlers.HTMLHandler.register_context_processor(set_context)


class MainHandler(handlers.HTMLHandler):
    def _get(self):
        return ('main.html', {'page_id':'main'})


class SearchHandler(handlers.HTMLHandler):
    def _get(self):
        query = self.request.get('q', '').strip()

        # immediately redirect to book page if given an ISBN as query
        if models.Book.ISBN13_REGEX.match(query) or models.Book.ISBN10_REGEX.match(query):
            isbn = pyisbn.convert(query) if len(query) == 10 else query
            self.redirect('/%s' % isbn)
            return (None, None)

        # otherwise, do a google book search
        context = {
            "page_title": u'Search: "%s"' % query,
            "page_id": 'search',
            "query": query,
            "books": []
        }
        hashed  = booksearch.hash_query(query)
        results = booksearch.search(query, hashed=hashed)

        if results:
            # if only has 1 result, immediately save and redirect
            if len(results) == 1:
                # no need to update=True since google book search results
                # rarely chagne...
                store_books(results, update=False)
                self.redirect('/%s' % results['isbn13'])
                return (None, None)

            # convert the resulting dict objects into temporary faux Book
            # entities for use in the template, then defer the actual
            # creation of the entities to a bg task
            for res in results:
                res['permalink'] = '/%s' % res['isbn13']
                res['links'] = defaultdict(lambda : '')
                for ln in res.get('_links', []):
                    res['links'][ln['name']] = ln['url']
            context['books'] = results

            # store books...
            logging.info('SearchHandler: storing of %d results' % len(results))
            models.store_books(results, update=False)

        return ('search.html', context)


class BookHandler(handlers.HTMLHandler):
    def _get(self, isbn):
        book  = models.Book.get_by_isbn(isbn, create=False)
        title = 'Book %s not found' % isbn

        if not book or not book.google_id or not book.amazon_id:
            results = booksearch.search('isbn:%s' % isbn)
            if results:
                # set update=True since this could be a direct page visit
                # and no book details have been stored yet (i.e. book info
                # saved during crawling)
                books = models.store_books(results, update=True)
                if books:
                    book = books[0]

        if book:
            title = book.title

        return ('view.html', {"isbn":isbn, "book":book, "page_title":title,
                              "shops":bookshop.SHOPS.keys()})


class FeedbackHandler(handlers.HTMLHandler):
    def _get(self, send=None):
        sent = (self.request.get('sent') == '1')
        return ('feedback.html', {"page_title":'Feedback', "message_sent":sent, "errors":{}, "fields":{}})

    def _post(self, send=None):
        fields = {
            "name": self.request.get('name').strip(),
            "email": self.request.get('email').strip(),
            "message": self.request.get('message').strip()
        }

        if fields['name'] and fields['email'] and fields['message']:
            mail.send_mail(
                sender='zaimworks@gmail.com',
                to='abuzaim@gmail.com',
                subject='Feedback message from %s' % fields['name'],
                reply_to=fields['email'],
                body=fields['message']
            )
            self.redirect('/feedback?sent=1')
            return (None, None)

        errors = {}
        for k, v in fields.iteritems():
            errors[k] = (not v)

        return ('feedback.html', {"page_title":'Feedback', "message_sent":False,
                                  "errors":errors, "fields":fields})


class PriceHandler(handlers.JSONHandler):
    def _get(self):
        isbn = self.request.get('isbn').strip()
        if not models.Book.ISBN13_REGEX.match(isbn):
            raise ValueError(u'Invalid ISBN')

        shop = self.request.get('shop').strip()
        if not shop:
            raise ValueError(u'Shop name not given')

        title  = self.request.get('title').strip()
        author = self.request.get('author').strip()

        if self.request.get('dbg'):
            return self._debug(isbn, shop, title, author)

        book = models.Book.get_by_isbn(isbn, defaults={'title':title, 'authors':[author]})

        # find in memcache/db first...
        prices = models.Price.find_for_book(book, shop)
        if prices:
            return prices

        # none found, so do actual page/scrape lookup
        prices  = bookshop.find(shop, isbn, title, author)
        objects = []
        if prices:
            # bookshop.find might return actual Price entities or just simple
            # dictionaries, separate the dicts and store them to get the
            # corresponding entities
            dicts = []
            for p in prices:
                if isinstance(p, models.Price):
                    objects.append(p)
                else:
                    p['book'] = book
                    dicts.append(p)
            objects.extend(models.store_prices(dicts, update=True))

        return objects

    def _debug(self, isbn, shop, title, author):
        prices, parser = bookshop.find(shop, isbn, title, author, debug=True)
        return prices


application = webapp.WSGIApplication([
    (r'/', MainHandler),
    (r'/search', SearchHandler),
    (r'/price', PriceHandler),
    (r'/([0-9]{13})', BookHandler),
    (r'/feedback(/send)?', FeedbackHandler),
    (r'/tasks/crawl', BookSourceTaskHandler),
], debug=settings.DEBUG)

def main():
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()

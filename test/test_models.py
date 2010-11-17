import datetime
import unittest
import traceback
import models
from google.appengine.ext import db, webapp
from google.appengine.ext.webapp import util

sample_books = [
    {
        "isbn13": '9781430224150',
        "isbn10": '1430224150',
        "title": 'Dive Into Python',
        "authors": ['Mark Pilgrim'],
        "publishers": ['Apress'],
        "published_date": datetime.date(2009, 1, 1),
        "description":
            "Mark Pilgrim's Dive Into Python 3 is a hands-on guide "
            "to Python 3 (the latest version of the Python language) "
            "and its differences from Python 2. As in the original "
            "book, Dive Into Python, each chapter starts with a "
            "real, complete code sample, proceeds to pick it apart "
            "and explain the pieces, and then puts it all back "
            "together in a summary at the end."
    },
    {
        "isbn13": '9781430218319',
        "isbn10": '1430218312',
        "title": 'Developing with Google App Engine',
        "authors": ['Eugene Ciurana'],
        "description":
            "Developing with Google App Engine introduces development with "
            "Google App Engine, a platform that provides developers and users "
            "with infrastructure Google itself uses to develop and deploy "
            "massively scalable applications."
    },
    {
        "isbn13": '9780596806026',
        "title": 'HTML5: Up and Running',
        "authors": ['Mark Pilgrim'],
        "description":
            "If you don't know about the new features available in HTML5, "
            "now's the time to find out. The latest version of this mark-up "
            "language is going to significantly change the way you develop "
            "web applications, and this book provides your first real look at "
            "HTML5's new elements and attributes. "
    }
]


class BaseTest:
    def setUp(self):
        self.sample  = dict([(b['isbn13'], b) for b in sample_books])
        self.objects = models.store_books(sample_books)

    def tearDown(self):
        total = len(self.sample)
        db.delete(self.objects)
        # this assumes maximum price/link objects created during test is ~300
        db.delete(models.Price.all(keys_only=True).fetch(total * 100))
        db.delete(models.Link.all(keys_only=True).fetch(total * 100))


class BookTest(BaseTest, unittest.TestCase):
    def testSetUp(self):
        created  = len(self.objects)
        expected = len(self.sample)
        self.assertEqual(created, expected, 'returned %d entities, expected %d' % (created, expected))

        for obj in self.objects:
            self.assertTrue(obj.isbn13 in self.sample, 'book id: %s not returned' % obj.isbn13)
            self.assertTrue(obj.is_saved(), 'object not saved')

            book = self.sample[obj.isbn13]
            for k, v in book.iteritems():
                self.assertTrue(hasattr(obj, k), 'object has no attr %s' % k)
                self.assertEqual(getattr(obj, k), v, 'object.%s != book[%s]' % (k, k))

    def testCreate(self):
        new = {
            "isbn13": '9780596158064',
            "title": 'Learning Python',
            "authors": ['Mark Lutz']
        }
        objects = models.store_books([new])

        returned = len(objects)
        self.assertEqual(returned, 1, 'returned %d entities, expected 1' % returned)

        obj = objects[0]
        self.assertTrue(obj.is_saved(), 'object not saved')
        self.assertEqual(obj.isbn13, new['isbn13'])
        self.assertEqual(obj.title, new['title'])
        self.assertEqual(obj.authors, new['authors'])

        all_books = models.Book.all().count()
        self.assertEqual(all_books, len(self.sample) + 1, 'book not added to datastore')

    def testUpdate(self):
        book = {
            "isbn13": '9781430224150',
            "google_id": 'ekrhtG-Hn5IC',
            "title": 'Dive Into Python 3'
        }
        objects = models.store_books([book], update=True)

        returned = len(objects)
        self.assertEqual(returned, 1, 'returned %d entities, expected 1' % returned)

        obj = objects[0]
        self.assertTrue(obj.is_saved(), 'object not saved')
        self.assertEqual(obj.isbn13, book['isbn13'])
        self.assertEqual(obj.google_id, book['google_id'])
        self.assertEqual(obj.title, book['title'])

        all_books = models.Book.all().count()
        expected  = len(self.sample)
        self.assertEqual(all_books, expected, 'book was added, not updated (expected %d books, got %d)' % (expected, all_books))

    def testCreateAndUpdate(self):
        books = {
            # create:
            "9780596158064": {
                "isbn13": '9780596158064',
                "title": 'Learning Python',
                "authors": ['Mark Lutz']
            },
            # update:
            "9781430224150": {
                "isbn13": '9781430224150',
                "google_id": 'ekrhtG-Hn5IC',
                "title": 'Dive Into Python 3'
            }
        }
        objects = models.store_books(books.values(), update=True)

        returned = len(objects)
        self.assertEqual(returned, 2, 'returned %d entities, expected 2' % returned)

        for obj in objects:
            book = books.get(obj.isbn13)
            for k, v in book.iteritems():
                self.assertEqual(book[k], getattr(obj, k), 'book[%s] != obj.%s' % (k, k))

        all_books = models.Book.all().count()
        expected  = len(self.sample) + 1
        self.assertEqual(all_books, expected, 'expected %d books, got %d' % (expected, all_books))


class PriceTest(BaseTest, unittest.TestCase):
    def setUp(self):
        super(PriceTest, self).setUp()
        book1 = self.objects[0]
        book2 = self.objects[1]
        self.price_sample = {
            'mph': {
                "book": book1,
                "source": 'mph',
                "price": 80.5
            },
            'mudah': {
                "book": book2,
                "source": 'mudah',
                "state": 1,
                "posted": datetime.date.today(),
                "price": 40.25,
                "url": 'http://example.com/'
            }
        }
        self.price_objects = models.store_prices(self.price_sample.values())

    def testCreate(self):
        returned = len(self.price_objects)
        expected = len(self.price_sample)
        self.assertEqual(returned, expected, 'returned %d entities, expected %d' % (returned, expected))

        for obj in self.price_objects:
            price = self.price_sample.get(obj.source)
            for k, v in price.iteritems():
                self.assertEqual(price[k], getattr(obj, k), 'price[%s] != obj.%s' % (k, k))

        all_prices = models.Price.all().count()
        self.assertEqual(all_prices, expected, 'expected %d prices, got %d' % (expected, all_prices))

    def testUpdate(self):
        price = self.price_sample['mudah']
        new = {
            "book": price['book'],
            "source": price['source'],
            "state": price['state'],
            "posted": price['posted'],
            # changed:
            "price": 43.25,
            "url": price['url'] + 'book/123/'
        }

        updated  = models.store_prices([new], update=True)
        returned = len(updated)
        self.assertEqual(returned, 1, 'returned %d entities, expected 1' % returned)

        for k, v in new.iteritems():
            self.assertEqual(new[k], getattr(updated[0], k), 'price[%s] != obj.%s' % (k, k))

        all_prices = models.Price.all().count()
        expected = len(self.price_sample)
        self.assertEqual(all_prices, expected, 'expected %d prices, got %d' % (expected, all_prices))

    def testCreateFromBook(self):
        book = self.sample['9780596806026'] # book 3 has no prices set up
        book['_prices'] = [
            {
                "source": 'times',
                "price": 42.42
            }
        ]

        objects  = models.store_books([book], update=True)
        returned = len(objects)
        self.assertEqual(returned, 1, 'returned %d entities, expected 1' % returned)

        obj = objects[0]
        obj_prices = obj.price_set.count()
        self.assertEqual(obj_prices, 1, 'obj.price_set returned %d entities, expected 1' % obj_prices)

        obj_price = obj.price_set.fetch(1)[0]
        for k, v in book['_prices'][0].iteritems():
            self.assertEqual(book['_prices'][0][k], getattr(obj_price, k), 'price[%s] != obj.%s' % (k, k))

        # re-test book dupe check, just in case
        all_books = models.Book.all().count()
        expected  = len(self.sample)
        self.assertEqual(all_books, expected, 'book was added, not updated (expected %d books, got %d)' % (expected, all_books))

        all_prices = models.Price.all().count()
        expected = len(self.price_sample) + 1
        self.assertEqual(all_prices, expected, 'expected %d prices, got %d' % (expected, all_prices))

    def testUpdateFromBook(self):
        book = self.sample[self.price_sample['mph']['book'].isbn13]
        book['_prices'] = [{
            "source": 'mph',
            "price": 90.5
        }]

        objects = models.store_books([book], update=True)
        returned = len(objects)
        self.assertEqual(returned, 1, 'returned %d entities, expected 1' % returned)

        obj = objects[0]
        obj_prices = obj.price_set.count()
        self.assertEqual(obj_prices, 1, 'obj.price_set returned %d entities, expected 1' % obj_prices)

        obj_price = obj.price_set.fetch(1)[0]
        for k, v in book['_prices'][0].iteritems():
            ov = getattr(obj_price, k)
            self.assertEqual(book['_prices'][0][k], ov, "price['%s'] != obj.%s (expected '%s', got '%s')" % (k, k, v, ov))

        # re-test book dupe check, just in case
        all_books = models.Book.all().count()
        expected  = len(self.sample)
        self.assertEqual(all_books, expected, 'book was added, not updated (expected %d books, got %d)' % (expected, all_books))

        all_prices = models.Price.all().count()
        expected = len(self.price_sample)
        self.assertEqual(all_prices, expected, 'expected %d prices, got %d' % (expected, all_prices))


# Fuck this:
#class LinkTest(BaseTest, unittest.TestCase):
#    def testCreate(self):
#        pass
#
#    def testUpdate(self):
#        pass
#
#    def testCreateFromBook(self):
#        pass
#
#    def testUpdateFromBook(self):
#        pass

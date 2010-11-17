import datetime
import re
import time
import urllib2
import django.utils.simplejson as json
from email.utils import formatdate
from google.appengine.api import users
from google.appengine.ext import db
from BeautifulSoup import BeautifulSoup, BeautifulStoneSoup

# Regular regular expressions
RE_RM       = re.compile(r'^RM')
RE_MYR      = re.compile(r'^MYR')
RE_NUM      = re.compile(r'([0-9\.]+)')
RE_ISBN     = re.compile(r'^([0-9]{13})$')
RE_CALLBACK = re.compile(r'^[a-z0-9_\.]+$')
RE_NEWLINE  = re.compile(r'(\r|\n)+')


def download(url, data=None, headers=None, timeout=None):
    if timeout:
        import socket
        socket.setdefaulttimeout(timeout)
    headers  = headers or {}
    request  = urllib2.Request(url, data=data, headers=headers)
    response = urllib2.urlopen(request)
    return response

def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i+n]


class PageParser(object):
    headers = None
    parser = BeautifulSoup

    def __init__(self):
        self._source = ''
        self._parsed = None
        self._url = None

    def search(self, **parameters):
        self._source = self.open(parameters)
        self._parsed = self.parser(self._source)
        return self.filter(self._parsed, parameters)

    def open(self, parameters):
        self._url = self.build_url(parameters)
        if self._url:
            res = download(self._url, self.headers)
            if res:
                return res.read()
        return None

    def build_url(self, parameters):
        raise NotImplementedError

    def filter(self, page, parameters):
        raise NotImplementedError

class XMLPageParser(PageParser):
    parser = BeautifulStoneSoup

class JSONPageParser(PageParser):
    parser = json.loads

class PageParserError(StandardError):
    pass


class GqlEncoder(json.JSONEncoder):
    # http://stackoverflow.com/questions/2114659/how-to-serialize-db-model-objects-to-json
    def default(self, obj):
        if hasattr(obj, '__json__'):
            return getattr(obj, '__json__')()

        if isinstance(obj, db.GqlQuery):
            return list(obj)

        elif isinstance(obj, db.Model):
            properties = obj.properties().items()
            output = {}
            for field, value in properties:
                output[field] = getattr(obj, field)
            return output

        elif isinstance(obj, datetime.datetime):
            output = {}
            fields = ['day', 'hour', 'microsecond', 'minute', 'month', 'second', 'year']
            methods = ['ctime', 'isocalendar', 'isoformat', 'isoweekday', 'timetuple']
            for field in fields:
                output[field] = getattr(obj, field)
            for method in methods:
                output[method] = getattr(obj, method)()
            output['epoch'] = time.mktime(obj.timetuple())
            return output

        elif isinstance(obj, datetime.date):
            output = {}
            fields = ['year', 'month', 'day']
            for field in fields:
                output[field] = getattr(obj, field)
            return output

        elif isinstance(obj, time.struct_time):
            return list(obj)

        elif isinstance(obj, users.User):
            output = {}
            methods = ['nickname', 'email', 'auth_domain']
            for method in methods:
                output[method] = getattr(obj, method)()
            return output

        return json.JSONEncoder.default(self, obj)

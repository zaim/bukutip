import os

DEBUG = os.environ['SERVER_SOFTWARE'].startswith('Development')
TEMPLATE_DIRS = [os.path.join(os.path.dirname(__file__), 'templates')]

# Book price configuration
EXCHANGE_RATE = {"USD": 3.095}

# Screen scraper user agent
USER_AGENT = 'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US) AppleWebKit/534.7 (KHTML, like Gecko) Chrome/7.0.517.41 Safari/534.7'

# API Keys
ISBNDB_KEY    = ''
AMAZON_KEY    = ''
AMAZON_SECRET = ''
AMAZON_ASSOC  = ''

# Global template context
CONTEXT = {
    "app_version": os.environ['CURRENT_VERSION_ID'],
    "site_title": u'BukuTip',
    "page_title": u'',
    "page_id": u'',
    "site_description": u'Search and compare book prices in Malaysia. MPH, Kinokuniya, Times, Bookxcess and more.'
}

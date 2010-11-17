"""Find book prices in various book shop websites"""

import urllib
import settings
from datetime import datetime
from zaim import utils
from models import Book, Price


class MPH(utils.PageParser):
    # 202.187.45.71
    # self.headers = {
    #    'Host': 'www.mphonline.com'
    # }
    URL = r'http://www.mphonline.com/books/nsearch.aspx?do=detail&pcode=%s'

    def build_url(self, parameters):
        try:
            isbn = parameters['isbn']
        except KeyError:
            raise utils.PageParserError('MPH parser requires the "isbn" parameter')
        return MPH.URL % isbn

    def filter(self, soup, parameters):
        content_id   = 'MPHOnline_ContentPlaceHolder1_LblContent'
        detail_cls   = 'detail_br'
        content_span = soup.find('span', id=content_id)
        if content_span:
            detail_table = content_span('table', {'class': detail_cls}, limit=1)
            if detail_table:
                price = detail_table[0](text=utils.RE_RM)
                if price:
                    m = utils.RE_NUM.search(price[0].strip())
                    if m:
                        return [{"price": float(m.group(0))}]
                    else:
                        raise utils.PageParserError("Price text mangled: %s" % price)
                else:
                    raise utils.PageParserError("No price text found")
            else:
                raise utils.PageParserError("No table.%s found" % detail_cls)
        else:
            raise utils.PageParserError("No span#%s found" % content_id)


class Times(utils.PageParser):
    # 203.116.11.137
    # self.headers = {
    #    'Host': 'www.timesbookstores.com.my'
    # }
    URL = r'http://www.timesbookstores.com.my/ProductDetail.aspx?item_code=%s'

    def build_url(self, parameters):
        try:
            return Times.URL % parameters['isbn']
        except KeyError:
            raise utils.PageParserError('Times parser requires the "isbn" parameter')

    def filter(self, soup, parameters):
        price_tag = soup.find('span', {'id':'ctl00_maincontent_lblPrice', 'class':'text_price'})
        if price_tag:
            price = price_tag.string.strip()
            if utils.RE_RM.match(price):
                m = utils.RE_NUM.search(price)
                if m:
                    return [{"price": float(m.group(0))}]
            raise utils.PageParserError("Price text mangled: %s" % price)
        else:
            raise utils.PageParserError("No price text found")


class Kinokuniya(utils.PageParser):
    # 210.165.4.71
    # self.headers = {
    #    'Host': 'bookweb.kinokuniya.co.jp'
    # }
    URL = r'http://bookweb.kinokuniya.co.jp/guest/cgi-bin/bookseaohb.cgi?KEYWORD=%s&AREA=05'

    def build_url(self, parameters):
        try:
            return Kinokuniya.URL % parameters['isbn']
        except KeyError:
            raise utils.PageParserError('Kinokuniya parser requires the "isbn" parameter')

    def filter(self, soup, parameters):
        price_tag = soup.find('font', {'color':'red'})
        if price_tag and price_tag.b:
            price = price_tag.b.string.strip()
            if utils.RE_MYR.match(price):
                m = utils.RE_NUM.search(price)
                if m:
                    return [{"price": float(m.group(0))}]
            raise utils.PageParserError("Price text mangled: %s" % price)
        else:
            raise utils.PageParserError("No price text found")


class Mudah(utils.PageParser):
    URL = 'http://www.mudah.my/li?ca=9_s&th=1&cg=5060&w=3&q=%s'

    def build_url(self, parameters):
        title  = parameters.get('title')
        author = parameters.get('author', '')
        if not title:
            raise utils.PageParserError('Mudah.my parser requires the "title" parameter')
        query = title.strip()
        if author:
            query = query + ' ' + author.strip()
        return Mudah.URL % urllib.quote_plus(query)

    def filter(self, soup, parameters):
        prices = []
        table  = soup.find('table', id='hl')

        if not table:
            return prices

        for row in table('tr', {"class":lambda c: not c=='google_listing_ad'}):
            date, url, price = datetime.today(), None, None

            # get item url and price
            tds = row.findAll('td', {"nowrap":'nowrap'})
            if len(tds) > 1:
                item_td = tds[0]
                for e in item_td:
                    if isinstance(e, unicode):
                        price_str = e.strip()
                        if utils.RE_RM.match(price_str):
                            m = utils.RE_NUM.search(price_str)
                            if m :
                                price = float(m.group(0))
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


class Bookxcess(object):
    def __init__(self):
        self._url = 'http://www.bookxcess.com/'

    def search(self, isbn, title, author):
        book = Book.get_by_isbn(isbn, defaults={"title":title, "authors":[author]})
        prices = Price.find_for_book(book, 'bookxcess')
        if prices:
            return prices
        else:
            return []


SHOPS = dict([(S.__name__.lower(), S) for S in (MPH, Times, Kinokuniya, Mudah, Bookxcess)])

def get_shop(id):
    Shop = SHOPS.get(id, None)
    if Shop:
        return Shop()
    return None

def find(shop, isbn, title='', author='', debug=False):
    if isinstance(shop, basestring):
        shopid = shop
        shop = get_shop(shopid)
        if shop is None:
            raise NameError('Shop "%s" not found' % shopid)
    elif isinstance(shop, utils.PageParser):
        shopid = shop.__class__.__name__.lower()
    else:
        raise TypeError('"shop" argument must be a string or a PageParser object')

    prices = shop.search(isbn=isbn, title=title, author=author)
    for p in prices:
        p['source'] = shopid
        if not p.get('url') and shop._url:
            p['url'] = shop._url

    return (prices, shop) if debug else prices

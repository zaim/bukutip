import settings
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util


class OpenIdLoginHandler(webapp.RequestHandler):
    def get(self):
        # force usage of gmail.com openid for now
        self.redirect(users.create_login_url('/', None, 'gmail.com'))

application = webapp.WSGIApplication([
    ('/_ah/login_required', OpenIdLoginHandler)
], debug=settings.DEBUG)

def main():
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()

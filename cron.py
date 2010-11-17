import datetime
import sys
import time
import urllib2
import os

tasks = [
    ("mph", {
        "callback": 'mph_rss',
        "schedule": 'every monday %s',
        "urls": [
            ("rss", [
                "http://www.mphonline.com/rss/bestsellers/fiction.xml",
                "http://www.mphonline.com/rss/bestsellers/nonfiction.xml"
            ]),
        ]
    }),
    ("bookxcess", {
        "callback": 'bookxcess_pdf',
        "schedule": '1st tuesday of month %s',
        "urls": [
            ("fiction-chd-ya", ["http://www.bookxcess.com/fiction.pdf", "http://www.bookxcess.com/chd.pdf", "http://www.bookxcess.com/ya.pdf"]),
            ("arcdesign-bio-business", ["http://www.bookxcess.com/arcdesign.pdf", "http://www.bookxcess.com/bio.pdf", "http://www.bookxcess.com/business.pdf"]),
            ("craft-cookery-general", ["http://www.bookxcess.com/craft.pdf", "http://www.bookxcess.com/cookery.pdf", "http://www.bookxcess.com/general.pdf"]),
            ("health-history-homegarden", ["http://www.bookxcess.com/health.pdf", "http://www.bookxcess.com/history.pdf", "http://www.bookxcess.com/homegarden.pdf"]),
            ("humour-musicmovie-politics", ["http://www.bookxcess.com/humour.pdf", "http://www.bookxcess.com/musicmovie.pdf", "http://www.bookxcess.com/politics.pdf"]),
            ("pets-poetry-puzzle", ["http://www.bookxcess.com/pets.pdf", "http://www.bookxcess.com/poetry.pdf", "http://www.bookxcess.com/puzzle.pdf"]),
            ("ref-relationship-science", ["http://www.bookxcess.com/ref.pdf", "http://www.bookxcess.com/relationship.pdf", "http://www.bookxcess.com/science.pdf"]),
            ("self-spiritual-sports", ["http://www.bookxcess.com/self.pdf", "http://www.bookxcess.com/spiritual.pdf", "http://www.bookxcess.com/sports.pdf"]),
            ("travel-newage-misc", ["http://www.bookxcess.com/travel.pdf", "http://www.bookxcess.com/newage.pdf", "http://www.bookxcess.com/misc.pdf"]),
            ("transport-artphoto-beauty", ["http://www.bookxcess.com/transport.pdf", "http://www.bookxcess.com/artphoto.pdf", "http://www.bookxcess.com/beauty.pdf"]),
            ("com-language-literary", ["http://www.bookxcess.com/com.pdf", "http://www.bookxcess.com/language.pdf", "http://www.bookxcess.com/literary.pdf"]),
            ("parenting-psycho-social", ["http://www.bookxcess.com/parenting.pdf", "http://www.bookxcess.com/psycho.pdf", "http://www.bookxcess.com/social.pdf"]),
            ("truecrime-truestories-comics", ["http://www.bookxcess.com/truecrime.pdf", "http://www.bookxcess.com/truestories.pdf", "http://www.bookxcess.com/comics.pdf"])
        ]
    })
]

every_minute = 30

def generate_yaml(out=False):
    yaml  = open('cron.yaml', 'r')
    start = ''
    for line in yaml:
        start += line
        if line.startswith('# TASKS'):
            break
    yaml.close()

    if not start:
        start = 'cron:\n'

    next = datetime.timedelta(minutes=every_minute)
    time = datetime.datetime(year=datetime.datetime.utcnow().year, month=1, day=4)
    time = time + datetime.timedelta(days=-time.weekday())
    yaml = ''
    for source, info in tasks:
        when = info['schedule']
        for name, _ in info['urls']:
            tstr  = when % time.strftime('%H:%M').lower()
            item  = "- description: crawl for %(source)s/%(name)s\n"
            item += "  url: /tasks/crawl?source=%(source)s&name=%(name)s\n"
            item += "  schedule: %(when)s\n"
            yaml += (item % {'source':source, 'name':name, 'when':tstr})
            time += next

    yaml = start + yaml
    if out:
        print yaml
    return yaml

def run_cron(out=True):
    min   = 7
    count = 0
    urls  = []
    mlen  = 0

    for source, info in tasks:
        for name, url in info['urls']:
            url = 'http://localhost:8080/tasks/crawl?source=%s&name=%s' % (source, name)
            if len(url) > mlen:
                mlen = len(url)
            urls.append(url)
            count += 1

    eta = float(count * min)
    met = 'minutes'
    if eta > 60:
        eta = eta / 60
        met = 'hours'

    print "Will run %d tasks every %d minutes" % (count, min)
    print "Approximate ETA: %.2f %s" % (eta, met)
    print "Continue? [y/N]",
    yn = raw_input()

    if not yn.lower() == 'y':
        return

    try:
        print
        complete = 0
        for i, url in enumerate(urls):
            res = None
            pad = '.' * (mlen - len(url))
            print '%02d/%02d] %s' % (i+1, count, url),
            if i > 0:
                time.sleep(min * 60)
            try:
                print '%s[' % pad,
                res = urllib2.urlopen(url)
            except urllib2.URLError:
                pass
            except urllib2.HTTPError, e:
                res = e
            if res and res.code == 200:
                code = res.code
                complete += 1
            else:
                if res: code = res.code
                else: code = 'failed'
            print '%s ]' % code
    except KeyboardInterrupt:
        print
        print "Interrupted: completed %d of %d tasks" % (complete, count)
        return

def help(out=True):
    print "Syntax: %s [generate_yaml|run_cron|help]" % sys.argv[0]

def main():
    cmd = 'help'
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

    command = {
        "generate_yaml": generate_yaml,
        "run_cron": run_cron,
        "help": help
    }.get(cmd, help)

    command((cmd == 'generate_yaml'))

if __name__ == '__main__':
    main()

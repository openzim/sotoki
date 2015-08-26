#!/usr/bin/env python2
"""sotoki.

Usage:
  sotoki.py load <dump-directory> <database-directory>
  sotoki.py build <templates> <database> <output>
  sotoki.py (-h | --help)
  sotoki.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

"""
import os
import re
from traceback import print_exc
from string import punctuation

from docopt import docopt

from markdown import markdown as md

from jinja2 import Environment
from jinja2 import FileSystemLoader

from lxml.etree import parse

from ajgudb import AjguDB
from ajgudb import gremlin as g


def intspace(value):
    orig = str(value)
    new = re.sub("^(-?\d+)(\d{3})", '\g<1> \g<2>', orig)
    if orig == new:
        return new
    else:
        return intspace(new)


def markdown(text):
    # FIXME: add postprocess step to transform 'http://' into a link
    # strip p tags
    return md(text)[3:-4]


def scale(number):
    """Convert number to scale to be used in style to color arrows
    and comment score"""
    if number < 0:
        return 'negative'
    if number == 0:
        return 'zero'
    if number < 3:
        return 'positive'
    if number < 8:
        return 'good'
    return 'verygood'


def render(output, template, templates, **context):
    templates = os.path.abspath(templates)
    env = Environment(loader=FileSystemLoader((templates,)))
    filters = dict(
        markdown=markdown,
        intspace=intspace,
        scale=scale,
        clean=lambda y: filter(lambda x: x not in punctuation, y)
    )
    env.filters.update(filters)
    template = env.get_template(template)
    page = template.render(**context)
    with open(output, 'w') as f:
        f.write(page.encode('utf-8'))


# load

# to_datetime = lambda x: datetime.strptime(x[:-4], '%Y-%m-%dT%H:%M:%S')


def load(dump, database):
    db = AjguDB(database)
    load_simple(db, os.path.join(dump, 'Tags.xml'))
    # load_simple(db, os.path.join(dump, 'Badges.xml'))
    load_simple(db, os.path.join(dump, 'Users.xml'))

    try:
        load_posts(db, os.path.join(dump, 'Posts.xml'))
    except Exception as exc:
        print('failed')
        print_exc(exc)

    try:
        load_post_links(db, os.path.join(dump, 'PostLinks.xml'))
    except Exception as exc:
        print('failed')
        print_exc(exc)

    try:
        load_comments(db, os.path.join(dump, 'Comments.xml'))
    except Exception as exc:
        print('failed')
        print_exc(exc)

    db.close()


def load_simple(db, filepath):
    filename = os.path.basename(filepath)
    kind = filename.split('.')[0][:-1]

    print '%s: load xml' % kind
    xml = parse(filepath)
    items = xml.getroot()

    print '%s: populate database' % kind
    for index, item in enumerate(items.iterchildren()):
        properties = dict(item.attrib)
        # make it faster to retrieve the object
        identifier = properties.pop('Id')
        properties['%sId' % kind] = identifier
        properties['kind'] = kind
        db.vertex(**properties)


def load_posts(db, filepath):
    filename = os.path.basename(filepath)
    kind = filename.split('.')[0][:-1]

    print '%s: load xml' % kind
    xml = parse(filepath)
    items = xml.getroot()

    questions = 0

    print '%s: populate database' % kind
    for index, item in enumerate(items.iterchildren()):
        properties = dict(item.attrib)
        properties['kind'] = kind
        # make it faster to retrieve the object
        identifier = properties.pop('Id')
        properties['%sId' % kind] = identifier

        # Score and favorite might be empty
        for key in ('Score', 'FavoriteCount'):
            try:
                value = properties[key]
            except:
                properties[key] = None
            else:
                properties[key] = int(value)

        # create post
        post = db.vertex(**properties)

        # link owner if any:
        try:
            owner = properties['OwnerUserId']
        except KeyError:
            pass
        else:
            try:
                owner = db.select(UserId=owner).one()
            except:
                pass
            else:
                post.link(owner, link="owner")

        # link with tags
        try:
            tags = properties['Tags']
        except KeyError:
            pass
        else:
            tags = tags[1:-1].split('><')

            for tag in tags:
                tag = db.select(TagName=tag).select(kind='Tag').one()
                post.link(tag, link='tag')

        # link with question if it's an answer
        if properties['PostTypeId'] == '2':
            # can't link answers to question since some answer come
            # before their question, links are created in another
            # step when all posts are loaded
            try:
                question = db.select(PostId=properties['ParentId']).one()
            except:
                pass
            else:
                question.link(post, link='answer')
        else:
            questions += 1

        if index == 50000:
            break
    print 'Post: there is %s questions' % questions


def load_post_links(db, filepath):
    filename = os.path.basename(filepath)
    kind = filename.split('.')[0][:-1]

    print '%s: load xml' % kind
    xml = parse(filepath)
    items = xml.getroot()

    print '%s: populate database' % kind
    for index, item in enumerate(items.iterchildren()):
        try:
            properties = dict(item.attrib)
            post = db.select(PostId=properties['PostId']).one()
            related = db.select(PostId=properties['RelatedPostId']).one()
            post.link(related, link='related', **properties)
            print('ok')
        except:
            pass


def load_comments(db, filepath):
    filename = os.path.basename(filepath)
    kind = filename.split('.')[0][:-1]

    print '%s: load xml' % kind
    xml = parse(filepath)
    items = xml.getroot()

    print '%s: populate database' % kind
    for index, item in enumerate(items.iterchildren()):
        properties = dict(item.attrib)
        properties['kind'] = kind

        try:
            value = properties['Score']
        except:
            properties['Score'] = None
        else:
            properties['Score'] = int(value)

        comment = db.vertex(**properties)

        # link post
        try:
            post = db.select(PostId=properties['PostId']).one()
        except Exception:
            pass
        else:
            post.link(comment, link='comment')

        try:
            user = db.select(UserId=properties['UserId']).one()
        except Exception:
            pass
        else:
            comment.link(user, link='author')


class StackExchangeDB(object):
    """Wrap AjguDB

    Make it easy to do the required queries in particular in the
    template. This serves as replacement for an ORM"""

    def __init__(self, db):
        self.db = db

    def questions(self):
        query = self.db.query(g.select(kind='Post', PostTypeId='1'), g.get)
        return query()

    def post_tags(self, post):
        query = self.db.query(g.outgoings, g.select(link='tag'), g.end, g.get)
        return query(post)

    def post_author(self, post):
        query = self.db.query(g.outgoings, g.select(link='owner'), g.end, g.get)
        try:
            return query(post)[0]
        except IndexError:
            return None

    def post_comments(self, post):
        query = self.db.query(g.outgoings, g.select(link='comment'), g.end, g.get)
        return query(post)

    def post_answers(self, post):
        query = self.db.query(g.outgoings, g.select(link='answer'), g.end, g.get)
        answers = query(post)
        answers.sort(key=lambda x: x['Score'], reverse=True)
        return answers

    def comment_author(self, post):
        query = self.db.query(g.outgoings, g.select(link='author'), g.end, g.get)
        try:
            return query(post)[0]
        except IndexError:
            return None



def build(templates, database, output):
    # wrap the actual database
    db = StackExchangeDB(AjguDB(database))

    print 'generate questions'
    os.makedirs(os.path.join(output, 'question'))

    for index, question in enumerate(db.questions()):
        print 'render post: ', question['PostId']
        filename = '%s.html' % question['PostId']
        filepath = os.path.join(output, 'question', filename)
        render(
            filepath,
            'post.html',
            templates,
            question=question,
            db=db,
        )
        if index == 10:
            break

    # print 'generate tags'
    # os.makedirs(os.path.join(output, 'tag'))
    # tags = db.select(kind='Tag').all()
    # for index, tag in enumerate(tags):
    #     print 'render tag: ', tag['TagName']
    #     filename = '%s.html' % tag['TagName']
    #     filepath = os.path.join(output, 'tag', filename)
    #     render(
    #         filepath,
    #         'tag.html',
    #         templates,
    #         tag=tag,
    #     )
    #     if index == 10:
    #         break

    print 'done'


if __name__ == '__main__':
    arguments = docopt(__doc__, version='sotoki 0.1')
    if arguments['load']:
        load(arguments['<dump-directory>'], arguments['<database-directory>'])
    elif arguments['build']:
        build(arguments['<templates>'], arguments['<database>'], arguments['<output>'])

#!/usr/bin/env python2
"""sotoki.

Usage:
  sotoki.py load <dump-directory> <database-directory>
  sotoki.py offline <database> <output>
  sotoki.py render <templates> <database> <output>
  sotoki.py (-h | --help)
  sotoki.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

"""
import os
import re
from urlparse import urlparse
from string import punctuation

from sqlalchemy import ForeignKey
from sqlalchemy import create_engine
from sqlalchemy.orm import backref
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import relationship
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

from jinja2 import Environment
from jinja2 import FileSystemLoader

from lxml.etree import parse as string2xml
from lxml.html import fromstring as string2html
from lxml.html import tostring as html2string

from wget import download
from docopt import docopt
from slugify import slugify
from markdown import markdown as md


DEBUG = os.environ.get('DEBUG', False)


# templating


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


def jinja(output, template, templates, **context):
    templates = os.path.abspath(templates)
    env = Environment(loader=FileSystemLoader((templates,)))
    filters = dict(
        markdown=markdown,
        intspace=intspace,
        scale=scale,
        clean=lambda y: filter(lambda x: x not in punctuation, y),
        slugify=slugify,
    )
    env.filters.update(filters)
    template = env.get_template(template)
    page = template.render(**context)
    with open(output, 'w') as f:
        f.write(page.encode('utf-8'))


# database models

Base = declarative_base()


class Tag(Base):

    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True)
    name = Column(String)


class QuestionTag(Base):

    __tablename__ = 'quetiontag'
    id = Column(Integer, primary_key=True)

    tag_id = Column(Integer, ForeignKey('tags.id'), index=True)
    tag = relationship("Tag", backref=backref('questions',))

    question_id = Column(Integer, ForeignKey('posts.id'), index=True)
    question = relationship("Post", backref=backref('tags',))


class User(Base):

    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    reputation = Column(Integer)
    created_at = Column(String)
    name = Column(String)
    website = Column(String)
    location = Column(String)
    bio = Column(String)
    views = Column(Integer)
    up_votes = Column(Integer)
    down_votes = Column(Integer)


class Post(Base):

    __tablename__ = 'posts'

    id = Column(Integer, primary_key=True)
    type = Column(Integer)

    score = Column(Integer)
    title = Column(String)
    body = Column(String)

    created_at = Column(String)
    closed_at = Column(String)
    last_active_date = Column(String)

    view_count = Column(Integer)
    favorite_count = Column(Integer)

    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    owner = relationship("User", backref=backref('questions', order_by=id))

    answer_id = Column(Integer, ForeignKey('posts.id'), nullable=True)

    parent_id = Column(Integer, ForeignKey('posts.id'), nullable=True, index=True)  # noqa
    question = relationship("Post", remote_side=id, backref=backref('answers', order_by=score.desc()), foreign_keys='Post.parent_id', order_by=score.desc())  # noqa


class Comment(Base):

    __tablename__ = 'comments'

    id = Column(Integer, primary_key=True)
    score = Column(Integer)
    text = Column(String)
    created_at = Column(String)

    post_id = Column(Integer, ForeignKey('posts.id'), index=True)
    post = relationship("Post", backref=backref('comments', order_by=created_at))  # noqa

    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    user = relationship("User")


class PostLink(Base):

    __tablename__ = 'post_links'

    id = Column(Integer, primary_key=True)

    type = Column(Integer)

    post_id = Column(Integer, ForeignKey('posts.id'), index=True)
    post = relationship("Post", foreign_keys='PostLink.post_id', backref=backref('links'))  # noqa

    related_id = Column(Integer, ForeignKey('posts.id'))
    related = relationship("Post", foreign_keys='PostLink.related_id', backref=backref('relateds'))  # noqa


def iterate(filepath):
    items = string2xml(filepath).getroot()
    for index, item in enumerate(items.iterchildren()):
        yield item.attrib


def make_session(database):
    uri = 'sqlite:///%s/db.sqlite' % database
    engine = create_engine(uri)
    Session = sessionmaker(bind=engine)
    session = Session()
    return session


def load(dump, database):
    session = make_session(database)
    Base.metadata.create_all(session.bind)

    print 'load tags'
    for tag in iterate(os.path.join(dump, 'Tags.xml')):
        tag = Tag(id=int(tag['Id']), name=tag['TagName'])
        session.add(tag)
        session.commit()

    print 'load users'
    for user in iterate(os.path.join(dump, 'Users.xml')):
        user = User(
            id=user['Id'],
            name=user['DisplayName'],
            reputation=user['Reputation'],
            created_at=user['CreationDate'],
            website=user.get('WebsiteUrl'),
            location=user.get('Location'),
            bio=user.get('AboutMe'),
            views=user.get('Views'),
            up_votes=user.get('UpVotes'),
            down_votes=user.get('DownVotes'),
        )
        session.add(user)
        session.commit()

    print 'load posts'
    for properties in iterate(os.path.join(dump, 'Posts.xml')):
        post = Post(
            id=properties['Id'],
            type=properties.get('PostTypeId', 3),
            parent_id=properties.get('ParentId', None),
            answer_id=properties.get('AcceptedAnswerId', None),
            created_at=properties['CreationDate'],
            score=properties['Score'],
            view_count=properties.get('ViewCount', 0),
            body=properties['Body'],
            owner_id=properties.get('OwnerUserId', None),
            closed_at=properties.get('ClosedDate', None),
            title=properties.get('Title', ''),
            favorite_count=properties.get('FavoriteCount', 0),
            last_active_date=properties['LastActivityDate'],
        )
        session.add(post)
        session.commit()
        tags = properties.get('Tags', '')
        tags = tags[1:-1].split('><')

        for tag in tags:
            try:
                tag = session.query(Tag).filter(Tag.name == tag).one()
            except NoResultFound:
                pass
            else:
                link = QuestionTag(tag_id=tag.id, question_id=post.id)
                session.add(link)
        session.commit()

    print 'load post links'
    for properties in iterate(os.path.join(dump, 'PostLinks.xml')):
        post_link = PostLink(
            id=properties['Id'],
            post_id=properties['PostId'],
            related_id=properties['RelatedPostId'],
            type=properties['LinkTypeId']
        )
        session.add(post_link)
        session.commit()

    print 'load comments'
    for properties in iterate(os.path.join(dump, 'Comments.xml')):
        comment = Comment(
            id=properties['Id'],
            post_id=properties['PostId'],
            score=properties['Score'],
            text=properties['Text'],
            created_at=properties['CreationDate'],
            user_id=properties.get('UserId'),
        )
        session.add(comment)
        session.commit()


def offline(database, output):
    print 'offlining images of %s in %s...' % (database, output)
    output = os.path.join(output, 'static', 'images')
    os.makedirs(output)
    session = make_session(database)
    # FIXME: lazily iterate over all posts
    for index, post in enumerate(session.query(Post)):
        print 'processing post id=%s (%s)' % (post.id, index)
        try:
            body = string2html(post.body)
        except:  # error during parse
            continue
        else:
            imgs = body.xpath('//img')
            if imgs:
                for img in imgs:
                    src = img.attrib['src']
                    try:
                        download(src, output)
                    except IOError:
                        img.attrib['src'] = '../static/missingimage.png'
                    else:
                        url = urlparse(src)
                        filename = url.path.split('/')[-1]
                        img.attrib['src'] = '../static/images/' + filename
                post.body = html2string(body)
                session.add(post)
                session.commit()
        if DEBUG and index == 20:
            break


def render(templates, database, output):
    # wrap the actual database
    session = make_session(database)

    print 'render questions'
    os.makedirs(os.path.join(output, 'question'))
    questions = session.query(Post).filter(Post.type == 1)
    for index, question in enumerate(questions):
        filename = '%s.html' % slugify(question.title)
        filepath = os.path.join(output, 'question', filename)
        print filepath, question.closed_at
        jinja(
            filepath,
            'question.html',
            templates,
            question=question,
            rooturl="..",
        )
        if DEBUG and index == 10:
            break

    print 'render tags'
    # index page
    tags = session.query(Tag).order_by(Tag.name)
    jinja(
        os.path.join(output, 'index.html'),
        'tags.html',
        templates,
        tags=tags,
        rooturl=".",
    )
    # tag page
    os.makedirs(os.path.join(output, 'tag'))
    for index, tag in enumerate(tags):
        dirpath = os.path.join(output, 'tag')
        tagpath = os.path.join(dirpath, '%s' % tag.name)
        os.makedirs(tagpath)
        print tagpath
        # build page using pagination
        offset = 0
        page = 1
        while offset is not None:
            fullpath = os.path.join(tagpath, '%s.html' % page)
            questions = session.query(QuestionTag)
            questions = questions.filter(QuestionTag.tag_id == tag.id)
            questions = questions.limit(11).offset(offset).all()
            questions = map(lambda x: x.question, questions)
            try:
                questions[10]
            except IndexError:
                offset = None
            else:
                offset += 10
            questions = questions[:10]
            jinja(
                fullpath,
                'tag.html',
                templates,
                tag=tag,
                index=page,
                questions=questions,
                rooturl="../..",
                hasnext=bool(offset),
                next=page + 1,
            )
            page += 1
        if DEBUG and index == 10:
            break


if __name__ == '__main__':
    arguments = docopt(__doc__, version='sotoki 0.1')
    if arguments['load']:
        load(arguments['<dump-directory>'], arguments['<database-directory>'])
    elif arguments['render']:
        render(arguments['<templates>'], arguments['<database>'], arguments['<output>'])  # noqa
    elif arguments['offline']:
        offline(arguments['<database>'], arguments['<output>'])

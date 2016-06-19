#!/usr/bin/env python2
"""sotoki.

Usage:
  sotoki.py run
  sotoki.py load <dump-directory> <database-directory>
  sotoki.py render <templates> <database> <output>
  sotoki.py render-users <templates> <database> <output>
  sotoki.py offline <output> <cores>
  sotoki.py (-h | --help)
  sotoki.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
"""
import re
import os
import shlex
import os.path
from hashlib import sha1
from distutils.dir_util import copy_tree
from urllib2 import urlopen
from string import punctuation
from subprocess import check_output

from multiprocessing import Pool
from multiprocessing import cpu_count

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import ForeignKey
from sqlalchemy import create_engine
from sqlalchemy.orm import backref
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import relationship
from sqlalchemy.schema import Sequence
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.ext.declarative import declarative_base

from jinja2 import Environment
from jinja2 import FileSystemLoader

from lxml.etree import parse as string2xml
from lxml.html import parse as html
from lxml.html import tostring as html2string

from PIL import Image
from resizeimage import resizeimage

from docopt import docopt
from slugify import slugify
from markdown import markdown as md
import pydenticon


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


class Badge(Base):

    __tablename__ = 'badges'

    id = Column(Integer, Sequence('badges_id_seq'), primary_key=True)
    name = Column(String)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    user = relationship("User")


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

    print 'load badges'
    for badge in iterate(os.path.join(dump, 'Badges.xml')):
        badge = Badge(
            user_id=badge['UserId'],
            name=badge['Name']
        )
        session.add(badge)
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


def download(url, output):
    response = urlopen(url)
    output = response.read()
    with open(output, 'b') as f:
        f.write(output)


def resize(filepath):
    fd = open(filepath, 'r')
    img = Image.open(fd)
    # hardcoded size based on website layyout
    img = resizeimage.resize_width(img, 540)
    img.save(filepath, img.format)
    fd.close()


def system(command):
    check_output(shlex.split(command))


def optimize(filepath):
    # based on mwoffliner code http://bit.ly/1HZgZeP
    ext = os.path.splitext(filepath)[1]
    if ext in ('.jpg', '.jpeg', '.JPG', '.JPEG'):
        system('jpegoptim --strip-all -m50 "%s"' % filepath)
    elif ext in ('.png', '.PNG'):
        # run pngquant
        cmd = 'pngquant --verbose --nofs --force --ext="%s" "%s"'
        cmd = cmd % (ext, filepath)
        system(cmd)
        # run advancecomp
        system('advdef -q -z -4 -i 5 "%s"' % filepath)
    elif ext in ('.gif', '.GIF'):
        system('gifsicle -O3 "%s" -o "%s"' % (filepath, filepath))
    else:
        print('* unknown file extension %s' % filepath)


def process(args):
    images, filepaths, uid = args
    count = len(filepaths)
    print 'offlining start', uid
    for index, filepath in enumerate(filepaths):
        print 'offline %s/%s (%s)' % (index, count, uid)
        try:
            body = html(filepath)
        except Exception as exc:  # error during xml parsing
            print exc
        else:
            imgs = body.xpath('//img')
            for img in imgs:
                src = img.attrib['src']
                ext = os.path.splitext(src)[1]
                filename = sha1(src).hexdigest() + ext
                out = os.path.join(images, filename)
                # download the image only if it's not already downloaded
                if not os.path.exists(out):
                    try:
                        download(src, out)
                    except:
                        # do nothing
                        pass
                    else:
                        # update post's html
                        src = '../static/images/' + filename
                        img.attrib['src'] = src
                        # finalize offlining
                        resize(out)
                        optimize(out)
            # does the post contain images? if so, we surely modified
            # its content so save it.
            if imgs:
                post = html2string(body)
                with open(filepath, 'w') as f:
                    f.write(post)
    print 'offlining finished', uid


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in xrange(0, len(l), n):
        yield l[i:i+n]


def offline(output, cores):
    """offline, resize and reduce size of images"""
    print 'offline images of %s using %s process...' % (output, cores)
    images_path = os.path.join(output, 'static', 'images')
    if not os.path.exists(images_path):
        os.makedirs(images_path)

    filepaths = os.path.join(output, 'question')
    filepaths = map(lambda x: os.path.join(output, 'question', x), os.listdir(filepaths))  # noqa
    filepaths_chunks = chunks(filepaths, len(filepaths) / cores)
    filepaths_chunks = list(filepaths_chunks)

    # start offlining
    pool = Pool(cores)
    # prepare a list of (images_path, filepaths_chunck) to feed
    # `process` function via pool.map
    args = zip([images_path]*cores, filepaths_chunks, range(cores))
    print 'start offline process with', cores, 'cores'
    pool.map(process, args)


def lazy(query):
    offset = 0
    while True:
        try:
            yield query.limit(1).offset(offset).one()
        except:
            raise StopIteration
        else:
            offset += 1


def render(templates, database, output):
    # wrap the actual database
    session = make_session(database)

    print 'render questions'
    os.makedirs(os.path.join(output, 'question'))
    questions = session.query(Post).filter(Post.type == 1)
    for index, question in enumerate(lazy(questions)):
        filename = '%s.html' % slugify(question.title)
        filepath = os.path.join(output, 'question', filename)
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


def render_users(templates, database, output):
    print 'render users'
    os.makedirs(os.path.join(output, 'user'))
    session = make_session(database)
    users = session.query(User)

    # Prepare identicon generation
    identicon_path = os.path.join(output, 'static', 'identicon')
    os.makedirs(identicon_path)
    # Set-up a list of foreground colours (taken from Sigil).
    foreground = [
        "rgb(45,79,255)",
        "rgb(254,180,44)",
        "rgb(226,121,234)",
        "rgb(30,179,253)",
        "rgb(232,77,65)",
        "rgb(49,203,115)",
        "rgb(141,69,170)"
    ]
    # Set-up a background colour (taken from Sigil).
    background = "rgb(224,224,224)"

    # Instantiate a generator that will create 5x5 block identicons
    # using SHA1 digest.
    generator = pydenticon.Generator(5, 5, foreground=foreground, background=background)  # noqa

    for index, user in enumerate(lazy(users)):
        username = slugify(user.name)

        # Generate big identicon
        padding = (20, 20, 20, 20)
        identicon = generator.generate(username, 164, 164, padding=padding, output_format="png")  # noqa
        filename = username + '.png'
        fullpath = os.path.join(output, 'static', 'identicon', filename)
        with open(fullpath, "wb") as f:
            f.write(identicon)

        # Generate small identicon
        padding = [0] * 4  # no padding
        identicon = generator.generate(username, 32, 32, padding=padding, output_format="png")  # noqa
        filename = username + '.small.png'
        fullpath = os.path.join(output, 'static', 'identicon', filename)
        with open(fullpath, "wb") as f:
            f.write(identicon)

        # generate user profile page
        filename = '%s.html' % username
        fullpath = os.path.join(output, 'user', filename)
        jinja(
            fullpath,
            'user.html',
            templates,
            user=user,
        )
        if DEBUG and index == 10:
            break


if __name__ == '__main__':
    arguments = docopt(__doc__, version='sotoki 0.1')
    if arguments['load']:
        load(arguments['<dump-directory>'], arguments['<database-directory>'])
    elif arguments['render']:
        render(arguments['<templates>'], arguments['<database>'], arguments['<output>'])  # noqa
    elif arguments['render-users']:
        render_users(arguments['<templates>'], arguments['<database>'], arguments['<output>'])  # noqa
    elif arguments['offline']:
        offline(arguments['<output>'], int(arguments['<cores>']))
    elif arguments['run']:
        # load dump into database
        database = 'work'
        dump = os.path.join('work', 'dump')
        load(dump, database)
        # render templates into `output`
        templates = 'templates'
        output = os.path.join('work', 'output')
        render(templates, database, output)
        render_users(templates, database, output)
        # offline images
        cores = cpu_count() / 2
        offline(output, cores)
        # copy static
        copy_tree('static', os.path.join('work', 'output', 'static'))

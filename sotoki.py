#!/usr/bin/env python2
"""sotoki.

Usage:
  sotoki.py run <url> <publisher> [--directory=<dir>]
  sotoki.py load <dump-directory> <database-directory>
  sotoki.py render <templates> <database> <output> <title> <publisher> [--directory=<dir>]
  sotoki.py render-users <templates> <database> <output> <title> <publisher> [--directory=<dir>]
  sotoki.py offline <output> <cores>
  sotoki.py (-h | --help)
  sotoki.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
  --directory=<dir>   Specify a directory for xml files [default: work/dump/]
"""
import sqlite3
import os
import xml.etree.cElementTree as etree
import logging

import re
import shlex
import os.path
from hashlib import sha1
from distutils.dir_util import copy_tree
from urllib2 import urlopen
from string import punctuation
from subprocess import check_output

from multiprocessing import Pool
from multiprocessing import cpu_count
from multiprocessing import Queue
from multiprocessing import Process

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

import bs4 as BeautifulSoup
import envoy
import sys
import datetime
import subprocess


class Worker(Process):
    def __init__(self, queue):
        super(Worker, self).__init__()
        self.queue= queue

    def run(self):
        print 'Computing things!'
        for data in iter( self.queue.get, None ):
            # Use data
            some_questions(data)




DEBUG = os.environ.get('DEBUG', False)

ANATHOMY = {
    'badges': {
        'Id': 'INTEGER',
        'UserId': 'INTEGER',
        'Name': 'TEXT',
        'Date': 'DATETIME',
        'Class': 'INTEGER',
        'TagBased' : 'INTEGER'
    },
    'comments': {
        'Id': 'INTEGER',
        'PostId': 'INTEGER',
        'Score': 'INTEGER',
        'Text': 'TEXT',
        'CreationDate': 'DATETIME',
        'UserId': 'INTEGER',
        'UserDisplayName': 'TEXT'
    },
    'posts': {
        'Id': 'INTEGER',
        'PostTypeId': 'INTEGER',  # 1: Question, 2: Answer
        'ParentID': 'INTEGER',  # (only present if PostTypeId is 2)
        'AcceptedAnswerId': 'INTEGER',  # (only present if PostTypeId is 1)
        'CreationDate': 'DATETIME',
        'Score': 'INTEGER',
        'ViewCount': 'INTEGER',
        'Body': 'TEXT',
        'OwnerUserId': 'INTEGER',  # (present only if user has not been deleted)
        'OwnerDisplayName': 'TEXT',
        'LastEditorUserId': 'INTEGER',
        'LastEditorDisplayName': 'TEXT',  # ="Rich B"
        'LastEditDate': 'DATETIME',  #="2009-03-05T22:28:34.823"
        'LastActivityDate': 'DATETIME',  #="2009-03-11T12:51:01.480"
        'CommunityOwnedDate': 'DATETIME',  #(present only if post is community wikied)
        'Title': 'TEXT',
        'Tags': 'TEXT',
        'AnswerCount': 'INTEGER',
        'CommentCount': 'INTEGER',
        'FavoriteCount': 'INTEGER',
        'ClosedDate': 'DATETIME'
    },
    'votes': {
        'Id': 'INTEGER',
        'PostId': 'INTEGER',
        'UserId': 'INTEGER',
        'VoteTypeId': 'INTEGER',
        # -   1: AcceptedByOriginator
        # -   2: UpMod
        # -   3: DownMod
        # -   4: Offensive
        # -   5: Favorite
        # -   6: Close
        # -   7: Reopen
        # -   8: BountyStart
        # -   9: BountyClose
        # -  10: Deletion
        # -  11: Undeletion
        # -  12: Spam
        # -  13: InformModerator
        'CreationDate': 'DATETIME',
        'BountyAmount': 'INTEGER'
    },
    'posthistory': {
        'Id': 'INTEGER',
        'PostHistoryTypeId': 'INTEGER',
        'PostId': 'INTEGER',
        'RevisionGUID': 'INTEGER',
        'CreationDate': 'DATETIME',
        'UserId': 'INTEGER',
        'UserDisplayName': 'TEXT',
        'Comment': 'TEXT',
        'Text': 'TEXT'
    },
    'postlinks': {
        'Id': 'INTEGER',
        'CreationDate': 'DATETIME',
        'PostId': 'INTEGER',
        'RelatedPostId': 'INTEGER',
        'PostLinkTypeId': 'INTEGER',
        'LinkTypeId': 'INTEGER'
    },
    'users': {
        'Id': 'INTEGER',
        'Reputation': 'INTEGER',
        'CreationDate': 'DATETIME',
        'DisplayName': 'TEXT',
        'LastAccessDate': 'DATETIME',
        'WebsiteUrl': 'TEXT',
        'Location': 'TEXT',
        'Age': 'INTEGER',
        'AboutMe': 'TEXT',
        'Views': 'INTEGER',
        'UpVotes': 'INTEGER',
        'DownVotes': 'INTEGER',
        'EmailHash': 'TEXT',
        'AccountId': 'INTEGER',
        'ProfileImageUrl': 'TEXT'
    },
    'tags': {
        'Id': 'INTEGER',
        'TagName': 'TEXT',
        'Count': 'INTEGER',
        'ExcerptPostId': 'INTEGER',
        'WikiPostId': 'INTEGER'
    }
}
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

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


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


def iterate(filepath):
    items = string2xml(filepath).getroot()
    for index, item in enumerate(items.iterchildren()):
        yield item.attrib


def download(url, output):
    response = urlopen(url)
    output_content = response.read()
    with open(output, 'w') as f:
        f.write(output_content)

def resize(filepath):
    if os.path.splitext(filepath)[1] in ('.jpg', '.jpeg', '.JPG', '.JPEG', '.png', '.PNG', '.gif', '.GIF'):
        img = Image.open(filepath)
        w, h = img.size
        if w >= 540:
            # hardcoded size based on website layyout
            try:
                img = resizeimage.resize_width(img, 540 ,  Image.ANTIALIAS)
            except:
                print "Problem with image : " + filepath
        #img.save(filepath, img.format, optimize=True,quality=50, progressive=True)
        img.save(filepath, img.format)

def optimize(filepath):
    # based on mwoffliner code http://bit.ly/1HZgZeP
    ext = os.path.splitext(filepath)[1]
    if ext in ('.jpg', '.jpeg', '.JPG', '.JPEG'):
        exec_cmd('jpegoptim --strip-all -m50 "%s"' % filepath)
    elif ext in ('.png', '.PNG'):
        # run pngquant
        cmd = 'pngquant --verbose --nofs --force --ext="%s" "%s"'
        cmd = cmd % (ext, filepath)
        exec_cmd(cmd)
        # run advancecomp
        exec_cmd('advdef -q -z -4 -i 5 "%s"' % filepath)
    elif ext in ('.gif', '.GIF'):
        exec_cmd('gifsicle -O3 "%s" -o "%s"' % (filepath, filepath))
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
                        try:
                            resize(out)
                            optimize(out)
                        except:
                            print "Something went wrong with" + out
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



def render_questions(templates, database, output, title, publisher, dump, cores):
    # wrap the actual database
    print 'render questions'
    db = os.path.join(dump, 'se-dump.db')
    conn = sqlite3.connect(db)
    conn.row_factory = dict_factory
    cursor = conn.cursor()
    #create table tags-questions
    cursor.execute("""CREATE TABLE IF NOT EXISTS questiontag(id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE, Score INTEGER, Title TEXT, CreationDate TEXT, Tag TEXT )""")
    conn.commit()
    questions = cursor.execute("""SELECT * FROM posts WHERE PostTypeId == 1""").fetchall()
    os.makedirs(os.path.join(output, 'question'))
    request_queue = Queue()
    for i in range(cores):
            Worker( request_queue ).start()
    for question in questions:
            question["Tags"] = question["Tags"][1:-1].split('><')
            for t in question["Tags"]:
                cursor.execute("INSERT INTO QuestionTag(Score, Title, CreationDate, Tag) VALUES(?, ?, ?, ?)""", (question["Score"], question["Title"], question["CreationDate"], t ))
            user = cursor.execute("SELECT DisplayName, Reputation  FROM users WHERE Id == ? ",( str(question["OwnerUserId"]),) ).fetchone()
            question["OwnerUserId"]=user
            question["comments"] = cursor.execute("SELECT * FROM comments WHERE Id == ? ",( str(question["Id"]), )).fetchall()
            for u in question["comments"]:
                tmp = cursor.execute("SELECT DisplayName  FROM users WHERE Id == ?", ( str(u["UserId"]),) ).fetchone()
                if tmp != None:
                    u["UserDisplayName"] = tmp["DisplayName"]
            question["answers"] = cursor.execute("SELECT * FROM posts WHERE PostTypeId == 2 AND ParentID == ? ",( str(question["Id"]),)).fetchall()
            for q in question["answers"]:
                user = cursor.execute("SELECT DisplayName, Reputation  FROM users WHERE Id == ? ", ( str(q["OwnerUserId"]),) ).fetchone()
                q["OwnerUserId"]=user
                q["comments"] = cursor.execute("SELECT * FROM comments WHERE Id == ? ",( str(q["Id"]),)).fetchall()
                for u in q["comments"]:
                    tmp = cursor.execute("SELECT DisplayName FROM users WHERE Id == ? " ,( str(u["UserId"]),) ).fetchone()
                    if tmp != None:
                        u["UserDisplayName"] = tmp["DisplayName"]
            tmp = cursor.execute("SELECT PostId FROM postlinks WHERE RelatedPostId == ? " ,( str(question["Id"]),) ).fetchall()
            question["relateds"] = [ ]
            for links in tmp:
                name =  cursor.execute("SELECT Title FROM posts WHERE Id == ? " ,( links["PostId"],) ).fetchone()
                if name != None:
                    question["relateds"].append( name["Title"] )
            data_send = [ templates, database, output, title, publisher, dump, question ]
            request_queue.put( data_send )
    conn.commit()
    for i in range(cores):
            request_queue.put( None )

def some_questions(args):
            templates, database, output, title, publisher, dump, question = args
            filename = '%s.html' % slugify(question["Title"])
            print filename
            filepath = os.path.join(output, 'question', filename)
            jinja(
                filepath,
                'question.html',
                templates,
                question=question,
                rooturl="..",
                title=title,
                publisher=publisher,
            )
def render_tags(templates, database, output, title, publisher, dump):
    print 'render tags'
    # index page
    db = os.path.join(dump, 'se-dump.db')
    conn = sqlite3.connect(db)
    conn.row_factory = dict_factory
    cursor = conn.cursor()

    tags = cursor.execute("""SELECT TagName FROM tags ORDER BY TagName""").fetchall()
    jinja(
        os.path.join(output, 'index.html'),
        'tags.html',
        templates,
        tags=tags,
        rooturl=".",
        title=title,
        publisher=publisher,
    )
    # tag page
    print "Render tag page"
    list_tag = map(lambda d: d['TagName'], tags)
    os.makedirs(os.path.join(output, 'tag'))
    for tag in list(set(list_tag)):
        dirpath = os.path.join(output, 'tag')
        tagpath = os.path.join(dirpath, '%s' % tag)
        os.makedirs(tagpath)
        print tagpath
        # build page using pagination
        offset = 0
        page = 1
        while offset is not None:
            fullpath = os.path.join(tagpath, '%s.html' % page)
            questions = cursor.execute("SELECT * FROM questiontag WHERE Tag = ? LIMIT 11 OFFSET ? ", ( str(tag), offset, ) ).fetchall()
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
                title=title,
                publisher=publisher,
            )
            page += 1
    conn.close()
def render_users(templates, database, output, title, publisher, dump):
    print 'render users'
    os.makedirs(os.path.join(output, 'user'))
    db = os.path.join(dump, 'se-dump.db')
    conn = sqlite3.connect(db)
    conn.row_factory = dict_factory
    cursor = conn.cursor()
    users = cursor.execute("""SELECT * FROM users""").fetchall()

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

    for user in users:
        username = slugify(user["DisplayName"])

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
            title=title,
            publisher=publisher,
        )
        if DEBUG and index == 10:
            break

def grab_title_description_favicon(url, output_dir):
    output = urlopen(url).read()
    soup = BeautifulSoup.BeautifulSoup(output)
    title = soup.find('meta',attrs={"name":u"twitter:title"})['content']
    description = soup.find('meta',attrs={"name":u"twitter:description"})['content']
    favicon = soup.find('link',attrs={"rel":u"image_src"})['href']
    if favicon[:2] == "//":
        favicon = "http:" + favicon
    favicon_out = os.path.join(output_dir, 'favicon.png')
    download(favicon, favicon_out)
    resize_image_profile(favicon_out)
    return [ title , description ]

def resize_image_profile(image_path):
    image = Image.open(image_path)
    w, h = image.size
    image = image.resize((48, 48), Image.ANTIALIAS)
    image.save(image_path)

def exec_cmd(cmd):
        return envoy.run(str(cmd.encode('utf-8'))).status_code

def create_zims(title, publisher, description):
        print 'Creating ZIM files'
        # Check, if the folder exists. Create it, if it doesn't.
        lang_input="en"
        html_dir = os.path.join("work", "output")
        zim_path = os.path.join("work/", "{title}_{lang}_all_{date}.zim".format(title=title.lower(),lang=lang_input,date=datetime.datetime.now().strftime('%Y-%m')))
        title = title.replace("-", " ")
        creator = title
        create_zim(html_dir, zim_path, title, description, lang_input, publisher, creator)

def create_zim(static_folder, zim_path, title, description, lang_input, publisher, creator):

    print "\tWritting ZIM for {}".format(title)
    context = {
        'languages': lang_input,
        'title': title,
        'description': description,
        'creator': creator,
        'publisher': publisher,
        'home': 'index.html',
        'favicon': 'favicon.png',
        'static': static_folder,
        'zim': zim_path
    }

    cmd = ('zimwriterfs --welcome="{home}" --favicon="{favicon}" '
           '--language="{languages}" --title="{title}" '
           '--description="{description}" '
           '--creator="{creator}" --publisher="{publisher}" "{static}" "{zim}"'
           .format(**context))
    print cmd

    if exec_cmd(cmd) == 0:
        print "Successfuly created ZIM file at {}".format(zim_path)
    else:
        print "Unable to create ZIM file :("

def bin_is_present(binary):
    try:
        subprocess.Popen(binary,
                         universal_newlines=True,
                         shell=False,
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         bufsize=0)
    except OSError:
        return False
    else:
        return True


def dump_files(file_names, anathomy,dump_path,
            dump_database_name='se-dump.db',
            create_query='CREATE TABLE IF NOT EXISTS {table} ({fields})',
            insert_query='INSERT INTO {table} ({columns}) VALUES ({values})',
            log_filename='se-parser.log'):
    logging.basicConfig(filename=os.path.join(dump_path, log_filename), level=logging.INFO)
    db = sqlite3.connect(os.path.join(dump_path, dump_database_name))
    for file in file_names:
        print
        "Opening {0}.xml".format(file)
        with open(os.path.join(dump_path, file + '.xml')) as xml_file:
            tree = etree.iterparse(xml_file)
            table_name = file

            sql_create = create_query.format(
                table=table_name,
                fields=", ".join(['{0} {1}'.format(name, type) for name, type in anathomy[table_name].items()]))
            print('Creating table {0}'.format(table_name))

            try:
                logging.info(sql_create)
                db.execute(sql_create)
            except Exception, e:
                logging.warning(e)

            for events, row in tree:
                try:
                    if row.attrib.values():
                        logging.debug(row.attrib.keys())
                        query = insert_query.format(
                            table=table_name,
                            columns=', '.join(row.attrib.keys()),
                            values=('?, ' * len(row.attrib.keys()))[:-2])
                        db.execute(query, row.attrib.values())
                        print ".",
                except Exception, e:
                    logging.warning(e)
                    print "x",
                finally:
                    row.clear()
            print "\n"
            db.commit()
            del (tree)


if __name__ == '__main__':
    arguments = docopt(__doc__, version='sotoki 0.1')
    if arguments['load']:
        load(arguments['<dump-directory>'], arguments['<database-directory>'])
    elif arguments['render']:
        render_questions(arguments['<templates>'], arguments['<database>'], arguments['<output>'], arguments['<title>'] , arguments['<publisher>'], arguments['    --directory'])
        render_tags(arguments['<templates>'], arguments['<database>'], arguments['<output>'], arguments['<title>'] , arguments['<publisher>'], arguments['--directory'])

    elif arguments['render-users']:
        render_users(arguments['<templates>'], arguments['<database>'], arguments['<output>'])  # noqa
    elif arguments['offline']:
        offline(arguments['<output>'], int(arguments['<cores>']))
    elif arguments['run']:
        if not bin_is_present("zimwriterfs"):
            sys.exit("zimwriterfs is not available, please install it.")
        # load dump into database
        url = arguments['<url>']
        publisher = arguments['<publisher>']
        dump = arguments['--directory']
        database = 'work'
        dump_files(ANATHOMY.keys(), ANATHOMY, dump)
        # render templates into `output`
        templates = 'templates'
        output = os.path.join('work', 'output')
        os.makedirs(output)
        cores = cpu_count() / 2
        if cores == 0:
            cores = 1
        title, description = grab_title_description_favicon(url, output)
        render_questions(templates, database, output, title, publisher, dump, cores)
        render_tags(templates, database, output, title, publisher, dump)
        render_users(templates, database, output, title, publisher, dump)
        # offline images
        offline(output, cores)
        # copy static
        copy_tree('static', os.path.join('work', 'output', 'static'))
        create_zims(title, publisher, description)

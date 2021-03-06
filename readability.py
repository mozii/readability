#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import re
# import math
import urlparse
import posixpath
from bs4 import BeautifulSoup


logger = logging.getLogger('readability')
logger.setLevel(logging.INFO)


REGEX_PATTERNS = {
    'unlikelyCandidates': "combx|comment|comments|cmt|cmts|community|disqus|extra|foot|header|menu|\
                           remark|rss|shoutbox|sidebar|sponsor|ad-break|agegate|\
                           pagination|pager|popup|tweet|twitter",  # x

    'okMaybeItsACandidate': "and|article|body|column|main|shadow|post",

    'socialPlugins': "linkwithin|jiathis",

    'positive': "article|body|content|entry|hentry|main|page|pagination|post|text|\
                 blog|story|footnote",  # x

    'negative': "combx|comment|cmt|com|contact|foot|footer|masthead|media|\
                 meta|outbrain|promo|related|scroll|shoutbox|sidebar|sponsor|\
                 shopping|tags|tool|widget",  # x

    'extraneous': "print|archive|comment|discuss|e[\-]?mail|share|reply|all|login|\
                   sign|single",

    'divToPElements': "<(a|blockquote|dl|div|img|ol|p|pre|table|ul)",  # x

    'replaceBrs': "<br[^>]*>[ \n\r\t]*",  # x

    'replaceFonts': "<(/?)font[^>]*>",  # x

    'shouldNotExist': "<wbr[^>]*>",  # x

    'normalize': "\s{2,}",

    'killBreaks': "(<br\s*/?>(\s|&nbsp;?)*)+",  # x

    'nextLink': "(next|weiter|continue|>([^\|]|$)|»([^\|]|$))",

    'prevLink': "(prev|earl|old|new|<|«)",
}


REGEX_OBJS = {}

for k, v in REGEX_PATTERNS.iteritems():
    REGEX_OBJS[k] = re.compile(v, re.IGNORECASE)


PURE_STRINGS_FILTER = ['\n']


def get_element_readable_string(e):
    s = ''
    for i in e.descendants:
        if isinstance(i, unicode):
            buf = i.strip()
            for j in PURE_STRINGS_FILTER:
                buf = buf.replace(j, '')
            s += buf
    return s


def format_html(html):
    """
    Replace deprecated tags
    """
    cleaned = REGEX_OBJS['shouldNotExist'].sub("", html)
    cleaned = REGEX_OBJS['replaceFonts'].sub("<\g<1>span>", cleaned)
    return cleaned


def remove_tag(node, tag):
    for e in node.find_all(tag):
        e.extract()


def remove_tags(node, tags):
    for e in node.find_all(True):
        if e.name in tags:
            e.extract()


def copy_node(node):
    return BeautifulSoup(unicode(node))


def fix_images_path(node, url):
    for img in node.find_all('img'):
        src = img.get('src')
        if not src:
            img.extract()
            continue

        if 'http://' != src[:7] and 'https://' != src[:8]:
            newSrc = urlparse.urljoin(url, src)

            newSrcArr = urlparse.urlparse(newSrc)
            newPath = posixpath.normpath(newSrcArr[2])
            newSrc = urlparse.urlunparse((newSrcArr.scheme, newSrcArr.netloc, newPath,
                                          newSrcArr.params, newSrcArr.query, newSrcArr.fragment))
            print 'new src', newSrc
            img['src'] = newSrc
    return node


def clean_node(node):
    # TODO replace brs

    # clean empty tags
    for e in node.find_all(['a', 'b', 'div', 'p', 'span', 'h*', 'article', 'section', 'ul', 'li']):
        # has image
        has_image = False
        for i in e.descendants:
            if hasattr(i, 'name') and i.name == 'img':
                has_image = True
                break
        if has_image:
            continue

        # has text
        if e.get_text().strip():  # .replace('\n', '')
            continue
        e.extract()

    # clean wrapper tags
    for e in node.find_all(['a', 'b', 'div', 'p', 'span', 'h*', 'article', 'section', 'ul', 'li']):
        if len(e.contents) == 1\
                and not isinstance(e.contents[0], unicode)\
                and e.contents[0].name not in ['img', 'b', 'strong', 'i']:
            e.contents[0].replace_with_children()

    # clean useless
    for e in node.find_all(True):
        if e.name == 'div':
            s = ''.join(map(unicode, e.contents))
            if not REGEX_OBJS['divToPElements'].search(s):
                e.name = 'p'

    # clean attributes
    def clean_attrs(_e):
        for i in ['class', 'id', 'style', 'align']:
            if i in _e.attrs:
                del _e.attrs[i]

    clean_attrs(node)
    for e in node.find_all(True):
        clean_attrs(e)

    # print 'cleared node'
    # print node.prettify()

    return node

    # text = unicode(node)

    # # clean on text level
    # text = REGEX_OBJS['killBreaks'].sub("<br />", text)


class Readability:
    """
    Find the deepest & largest node in a html tree

    Usage:

    >>> parser = Readability(html, url)
    >>> parser.title
    # title of the article
    >>> parser.article
    # main body
    """
    USELESS_TAGS = ['script', 'style', 'link', 'textarea']

    FACTORS = {
        'text': 100,
        'elimination': 5,
        'negative': 10,
        'positive': 10,
        'p_br': 1,
        'comma': 10,
        'priority_compare': 1.66,  # 60%
        'text_tag': 0.6,
        'children': 10
    }

    CHINESE_CHARS = {
        'comma': u'\uff0c',
    }

    DEBUG = False

    def __init__(self, source, url=None):
        assert isinstance(source, unicode), 'source should be unicode'
        self.url = url

        self.raw_source = source

        # the incomplete <p> or </p> will be fixed when soup is constructed
        self.source = format_html(source)

        # Force BeautifulSoup to use lxml as parser (lxml is the best, others may cause problems)
        self.soup = BeautifulSoup(self.source, 'lxml')

        # NOTE There is a stange thing in b4.__version__ 4.0.4 (currently 4.0.3)
        # that after clean the USELESS_TAGS, <title> in <head> is missing,
        # still don't know where the problem is.
        self.title = u''
        try:
            self.title = self.soup.find('title').text.strip()
        except:
            pass
        logging.info(u'got html title: %s', self.title)

        remove_tags(self.soup, self.USELESS_TAGS)

        # Get most possible nodes
        unsort_tops = self.get_readable_nodes()
        if len(unsort_tops) == 1:
            tops = unsort_tops
        else:
            tops = sorted(unsort_tops, key=lambda x: x['priority'], reverse=True)

        self.tops = tops

        self.winner = self.tops[0]

        # use copy_node to prevent winner node from changed
        self.article = clean_node(copy_node(self.winner['node']))
        if self.url:
            self.article = fix_images_path(self.article, self.url)

    def get_readable_nodes(self):
        """
        Player::
            node
            deepth
            children_num
            text_len
            priority
        """
        self.players = []

        # NOTE Traversal of the tree should be as less as possible
        for e in self.soup.body.find_all(True):
            # If no `__dict__`, its a already removed tag (include children of the removed tag)
            if not e.__dict__:
                continue

            # Filter the impossible nodes semantically before go into play
            id_and_class_list = []
            if e.get('id'):
                id_and_class_list.append(e.get('id'))
            if e.get('class'):
                id_and_class_list += (e.get('class'))
            id_and_class = '_'.join(id_and_class_list)

            # Remove social plugins
            if REGEX_OBJS['socialPlugins'].search(id_and_class) or\
                    (REGEX_OBJS['unlikelyCandidates'].search(id_and_class) and
                     not REGEX_OBJS['positive'].search(id_and_class)):
                logger.debug('Reject a node and its children, class & id: %s' % id_and_class)
                # Use `decompose` instead of `extract` to avoid iteration of the removed tags' children
                e.decompose()
                continue

            # Clean empty tags
            #if e.name in ['a', 'b', 'div', 'p', 'span', 'h*', 'article', 'section', 'ul', 'li']\
                #and (not e.contents or (isinstance(e.contents[0], basestring) and not e.contents[0].strip())):
                #e.extract()

        # NOTE If filtering and player initializing are in same loop,
        # player's information may not be properly calculated.
        # So seperate them in two loops, means, two traversal of the whole tree
        for e in self.soup.body.find_all(True):

            player = {
                'node': e,
                'deepth': len(list(e.parents)) - 1,
                'children_num': len(e.contents),
                # When counting text length, ` ` and `\n` should not be in place
                'text_len': len(e.get_text().strip().replace('\n', '').replace(' ', '')),
                'previous_priority': 0,
                'negative_score': 0,
                'positive_score': 0,
                'p_br_num': 0,
                'comma_num': 0,
            }

            # alternative algorithm
            # priority = math.sqrt(player['deepth'] * player['text_len'])
            player['priority'] = player['deepth'] * player['text_len'] / self.FACTORS['text']

            self.players.append(player)

        # round one, get the front players by basic priority
        # and affect their priority by tags & children tags
        self.priority_desc_players = sorted(self.players, key=lambda x: x['priority'], reverse=True)
        next_round = self.priority_desc_players[:self.FACTORS['elimination']]

        logger.debug('# round one processing: basic front players')
        self._print_players(next_round)
        self._debug_round('one', next_round)

        for p in next_round:
            # Text tags
            if p['node'].name in ('p', 'b', 'span', 'i', ):
                p['priority'] = p['priority'] * self.FACTORS['text_tag']

            p['priority'] += p['children_num'] * self.FACTORS['children']

        logger.debug('# round one over')
        self._print_players(next_round)
        self._debug_round('one', next_round)

        # Skip all next steps, this is for test use.
        return next_round

        # round two, players that smaller than the biggest after multiplys priority factor will be rejected
        current_players = next_round
        next_round = []
        for loop, p in enumerate(current_players):
            go_next = True
            if loop != 0:
                if p['priority'] * self.FACTORS['priority_compare'] < current_players[0]['priority']:
                    go_next = False
            if go_next:
                next_round.append(p)
        logger.debug('# round two over')
        self._print_players(next_round)
        self._debug_round('two', next_round)

        if len(next_round) == 1:
            return next_round

        # Currently stop using this, because what this round wants to do
        # can be easily done in round one (calculate children numbers)
        # round three, player who is the parent of another player will be rejected
        if False:
            current_players = next_round
            next_round = []
            for loop, p in enumerate(current_players):
                go_final = True
                for j in current_players[:loop] + current_players[loop + 1:]:
                    if p['node'] in list(j['node'].parents):
                        go_final = False
                if go_final:
                    next_round.append(p)
            logger.debug('# round three over')
            self._print_players(next_round)
            self._debug_round('three', next_round)

            if len(next_round) == 1:
                return next_round

        # final round, affect priority in several ways:
        # 1. try to math negative and positive words in node and descendants' id and classes
        # 2. count the <p> tag number in node
        # 3. count commas, include EN and CN characters
        current_players = next_round
        for loop, player in enumerate(current_players):
            player['previous_priority'] = player['priority']
            node = player['node']
            offset = 0

            # 1. by id and class
            id_and_classes = []
            cal_list = node.find_all(True)
            cal_list.insert(0, node)
            for e in cal_list:
                if e.get('id'):
                    id_and_classes.append(e.get('id'))
                id_and_classes.extend(e.get('class', []))

            negative_score = 0
            positive_score = 0
            for i in id_and_classes:
                if REGEX_OBJS['negative'].search(i) and\
                        not REGEX_OBJS['positive'].search(i):
                    logger.debug('top %s find negative %s' % (loop, i))
                    negative_score += 1

                if REGEX_OBJS['positive'].search(i) and\
                        not REGEX_OBJS['negative'].search(i):
                    positive_score += 1
            # test.debug('negative score %s' % negative_score)
            # test.debug('positive_score %s' % positive_score)
            offset -= negative_score * self.FACTORS['negative']
            offset += positive_score * self.FACTORS['positive']
            player['negative_score'] = negative_score
            player['positive_score'] = positive_score

            # 2. by <p> and <br> number
            p_br_num = len(node.find_all('p')) + len(node.find_all('br'))
            # test.debug('p br num %s' % p_br_num)
            offset += p_br_num / self.FACTORS['p_br']
            player['p_br_num'] = p_br_num

            # 3. by comma(symbo) number
            node_text = node.get_text()
            comma_num = node_text.count(',')
            comma_num += node_text.count(self.CHINESE_CHARS['comma'])
            # test.debug('comma_num %s' % comma_num)
            offset += comma_num / self.FACTORS['comma']
            player['comma_num'] = comma_num

            player['offset'] = offset
            player['priority'] += offset * 4

        logger.debug('# final round over')
        self._print_players(current_players)

        return current_players

    def _print_players(self, players):
        if not self.DEBUG:
            return
        for i in players:
            logger.debug(
                'deepth:%s text_len:%s priority:%s pre_priority:%s -score:%s +score:%s p_br_num:%s comma_num:%s' %
                (i['deepth'], i['text_len'], i['priority'], i['previous_priority'], i['negative_score'], i['positive_score'], i['p_br_num'], i['comma_num']))
            logger.debug('    ' + i['node'].get_text().strip().replace('\n', '')[:100])

    def _debug_round(self, name, players):
        if not self.DEBUG:
            return
        for loop, i in enumerate(players):
            with open('round_%s_%s.html' % (name, loop), 'w') as f:
                f.write(str(i['node']))


if __name__ == '__main__':
    import requests

    html = requests.get('http://blog.hucheng.com/articles/482.html').content
    parser = Readability(html.decode('utf8'))

    print parser.title
    print parser.article
    print parser.article.get_text()

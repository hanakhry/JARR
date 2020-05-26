import html
import logging
import re
from functools import lru_cache

from goose3 import Goose
from lxml import etree

from jarr.bootstrap import conf
from jarr.controllers.article import to_vector
from jarr.lib.enums import ArticleType, FeedType

logger = logging.getLogger(__name__)
IMG_ALT_MAX_LENGTH = 100
YOUTUBE_RE = re.compile(
        r'^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube\.com|youtu.be))'
        r'(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$')


def is_embedded_link(link):
    return YOUTUBE_RE.match(link)


class ContentGenerator:
    article_type = None
    feed_type = None

    def __init__(self, article):
        self.article = article
        self._page = None
        self.extracted_infos = {}

    def _get_goose(self):
        goose = Goose({"browser_user_agent": conf.crawler.user_agent})
        try:
            self._page = goose.extract(self.article.link)
        except Exception as error:
            logger.error("something wrong happened while trying to fetch "
                         "%r: %r", self.article.link, error)
        if not self._page:
            return False
        lang = self._page.opengraph.get('locale') or self._page.meta_lang
        self.extracted_infos['lang'] = lang
        self.extracted_infos['link'] = self._page.final_url
        keywords = set(self._page.meta_keywords.split(', '))
        self.extracted_infos['tags'] = set(self._page.tags).union(keywords)
        self.extracted_infos['title'] = self._page.title
        return True

    def get_vector(self):
        if self._page is None:
            self._get_goose()
        if self._page and self.extracted_infos:
            return to_vector(self.extracted_infos, self._page)

    def _from_goose_to_html(self, encoding="utf8"):
        result = ""
        current_node = self._page.top_node
        while True:
            result += etree.tostring(current_node,
                                     encoding=encoding).decode(encoding)
            current_node = current_node.getnext()
            if current_node is None:
                break
        return result

    @staticmethod
    def generate():
        return False, {}


class ImageContentGenerator(ContentGenerator):
    article_type = ArticleType.image

    def get_vector(self):
        return None

    def generate(self):
        logger.info('%r constructing image content from article',
                    self.article)
        text = self.article.title or self.article.content
        content = {'type': self.article.article_type.value,
                   'alt': html.escape(text[:IMG_ALT_MAX_LENGTH]),
                   'src': self.article.link}
        return True, content


class EmbeddedContentGenerator(ContentGenerator):
    article_type = ArticleType.embedded

    def get_vector(self):
        return None

    def generate(self):
        yt_match = YOUTUBE_RE.match(self.article.link)
        if yt_match:
            logger.info('%r constructing embedded youtube content '
                        'from article', self.article)
            try:
                return True, {'type': self.article.article_type.value,
                              'player': 'youtube',
                              'videoId': yt_match.group(5)}
            except IndexError:
                pass
        else:
            logger.warning('embedded video not recognized %r',
                           self.article.link)
        return True, {}


class TruncatedContentGenerator(ContentGenerator):

    def generate(self):
        if self._page is None:
            self._get_goose()
        success, content = False, {'type': 'fetched'}
        try:
            content['content'] = self._from_goose_to_html()
            content['link'] = self._page.final_url
            success = True
        except Exception:
            logger.exception("Could not rebuild parsed content for %r",
                             self.article)
        if success and self.article.comments:
            content['comments'] = self.article.comments
        logger.debug('%r no special type found doing nothing', self.article)
        return success, content


class RedditContentGenerator(TruncatedContentGenerator):
    feed_type = FeedType.reddit

    @property
    def is_pure_reddit_post(self):
        if self.article.article_type is not None:
            return False
        if self.article.link == self.article.comments:
            return True
        try:
            head = requests.head(self.article.comments, allow_redirects=True,
                                 timeout=conf.crawler.timeout)
            head.raise_for_status()
        except Exception:
            return False
        if self.article.link == head.url:
            return True
        return False

    def get_vector(self):
        if not self.is_pure_reddit_post:
            return super().get_vector()

    def generate(self):
        if not self.is_pure_reddit_post:
            return super().generate()
        return False, {}  # original reddit post, nothing to process


CONTENT_GENERATORS = {}


def feed_mapping(subcls_):
    if subcls_.feed_type:
        CONTENT_GENERATORS[subcls_.feed_type] = subcls_
    if subcls_.article_type:
        CONTENT_GENERATORS[subcls_.article_type] = subcls_


for subcls in ContentGenerator.__subclasses__():
    feed_mapping(subcls)
    for subsubcls in subcls.__subclasses__():
        feed_mapping(subsubcls)


@lru_cache()
def get_content_generator(article):
    if article.article_type and article.article_type in CONTENT_GENERATORS:
        return CONTENT_GENERATORS[article.article_type](article)

    if article.feed.feed_type \
            and article.feed.feed_type in CONTENT_GENERATORS:
        return CONTENT_GENERATORS[article.feed.feed_type](article)

    if article.feed.truncated_content:
        return TruncatedContentGenerator(article)

    return ContentGenerator(article)

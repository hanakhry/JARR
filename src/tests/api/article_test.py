from datetime import datetime
from tests.base import JarrFlaskCommon
from tests.api.common import ApiCommon
from web.controllers import UserController


class ArticleApiTest(JarrFlaskCommon, ApiCommon):
    urn = 'article'
    urns = 'articles'

    def test_api_list(self):
        resp = self._api('get', self.urns,
                         data={'feed_id': 1, 'order_by': '-id'},
                         user='user1')
        self.assertEquals(200, resp.status_code)
        self.assertEquals(3, len(resp.json()))
        self.assertTrue(resp.json()[0]['id'] > resp.json()[-1]['id'])

        resp = self._api('get', self.urns,
                         data={'category_id': 1}, user='user1')
        self.assertEquals(200, resp.status_code)
        self.assertEquals(3, len(resp.json()))

        resp = self._api('get', self.urns, data={'limit': 1}, user='user1')
        self.assertEquals(200, resp.status_code)
        self.assertEquals(1, len(resp.json()))

        resp = self._api('get', self.urns, user='admin')
        self.assertEquals(200, resp.status_code)
        self.assertEquals(10, len(resp.json()))

        resp = self._api('get', self.urns, data={'limit': 200}, user='admin')
        self.assertEquals(200, resp.status_code)
        self.assertEquals(36, len(resp.json()))

    def test_article_challenge_method(self):
        articles = self._api('get', self.urns, user='user1').json()
        UserController().update({'login__in': ['admin', 'user2']},
                                {'is_api': True})
        # admin knows this article (he knows them all)
        resp = self._api('get', 'articles/challenge', user='admin',
                data={'ids': [{'id': art['id']} for art in articles]})
        self.assertEquals(204, resp.status_code)
        # admin knows this article (he knows them all)
        resp = self._api('get', 'articles/challenge', user='admin',
                data={'ids': [{'id': art['id']} for art in articles]})
        self.assertEquals(204, resp.status_code)
        # user2 doesn't know user1 article, will consider them as knew
        resp = self._api('get', 'articles/challenge', user='user2',
                data={'ids': [{'id': art['id']} for art in articles]})
        self.assertEquals(10, len(resp.json()))
        # fake ids won't be recognised either and considered as new
        resp = self._api('get', 'articles/challenge', user='user2',
                data={'ids': [{'entry_id': art['id']} for art in articles]})
        self.assertEquals(10, len(resp.json()))

    def test_full_add(self):
        retrieved_date_utc = '2016-11-18T11:19:32.932015+00:00'
        data = {'entry_id': 'tag:1pxsolidblack.pl,2013-12-09:'
                            'apache-webdav-file-server.html',
                'feed_id': 1, 'user_id': 2, 'content': 'test',
                'date': '2013-12-09T20:20:00+00:00',
                'retrieved_date': '2016-11-18T23:19:32.932015+12:00',
                'tags': ['auto-hébergement', 'apache', 'webdav'],
                'link': '//1pxsolidblack.pl/apache-webdav-file-server.html',
                'title': 'Servir et gérer des fichiers avec\xa0WebDav'}

        resp = self._api('post', self.urn, user='admin', data=data)
        self.assertEquals(201, resp.status_code)
        self.assertEquals(data['date'], resp.json()['date'])
        self.assertEquals(retrieved_date_utc,
                          resp.json()['retrieved_date'])

        resp = self._api('get', '%s/%d' % (self.urn, resp.json()['id']),
                         user='admin', data=data)
        self.assertEquals(200, resp.status_code)
        self.assertEquals(data['date'], resp.json()['date'])
        self.assertEquals(retrieved_date_utc,
                          resp.json()['retrieved_date'])

    def test_api_creation(self):
        resp = self._api('post', self.urn, user='user1', data={'feed_id': 1})
        self.assertEquals(403, resp.status_code)
        UserController().update({'login': 'user1'}, {'is_api': True})

        resp = self._api('post', self.urn, user='user1',
                         data={'feed_id': 1,
                               'date': datetime.utcnow(),
                               'tags': ['tag1', 'tag2']})
        content = resp.json()
        self.assertEquals(201, resp.status_code)
        self.assertEquals(2, content['user_id'])
        self.assertEquals(['tag1', 'tag2'], content['tags'])

        resp = self._api('get', "%s/%s" % (self.urn, content['id']))
        self.assertEquals(['tag1', 'tag2'], resp.json()['tags'])

        resp = self._api('post', self.urn, user='user1', data={'feed_id': 1})
        self.assertEquals(2, resp.json()['user_id'])
        self.assertEquals(201, resp.status_code)

        resp = self._api('post', self.urn, user='user2',
                data={'user_id': 2, 'feed_id': 1})
        self.assertEquals(403, resp.status_code)
        UserController().update({'login': 'user2'}, {'is_api': True})

        resp = self._api('post', self.urn, user='user2',
                data={'user_id': 2, 'feed_id': 1})
        self.assertEquals(404, resp.status_code)

        resp = self._api('post', self.urns, user='user1',
                data=[{'feed_id': 1,
                       'date': datetime.utcnow(),
                       'tags': ['tag1', 'tag2']},
                      {'feed_id': 1,
                       'date': datetime.utcnow(),
                       'tags': ['tag1', 'tag2']}])

        self.assertEquals(201, resp.status_code)
        self.assertTrue(['ok', 'ok'], resp.json())

        resp = self._api('post', self.urns, user='user1',
                data=[{'feed_id': 1}, {'feed_id': 5}])
        self.assertEquals(206, resp.status_code)
        self.assertTrue(isinstance(resp.json()[0], dict))
        self.assertEquals('404: Not Found', resp.json()[1])

        resp = self._api('post', self.urns, user='user1',
                data=[{'user_id': 1, 'feed_id': 6}, {'feed_id': 5}])
        self.assertEquals(500, resp.status_code)
        self.assertEquals(['404: Not Found', '404: Not Found'], resp.json())

    def test_api_edit_feed_id(self):
        resp = self._api('get', self.urns, data={'limit': 1}, user='user1')
        self.assertEquals(1, len(resp.json()))
        self.assertEquals(200, resp.status_code)
        obj = resp.json()[0]
        resp = self._api('get', 'feeds', data={'limit': 1}, user='user2')
        self.assertEquals(1, len(resp.json()))
        self.assertEquals(200, resp.status_code)
        feed = resp.json()[0]
        resp = self._api('put', self.urn, obj['id'], user='user1',
                         data={'feed_id': feed['id']})
        self.assertEquals(400, resp.status_code)

    def test_api_edit_category_id(self):
        resp = self._api('get', self.urns, data={'limit': 1}, user='user1')
        self.assertEquals(1, len(resp.json()))
        self.assertEquals(200, resp.status_code)
        obj = resp.json()[0]
        resp = self._api('get', 'categories', data={'limit': 1}, user='user2')
        self.assertEquals(1, len(resp.json()))
        self.assertEquals(200, resp.status_code)
        category = resp.json()[0]
        resp = self._api('put', self.urn, obj['id'], user='user1',
                         data={'category_id': category['id']})
        self.assertEquals(400, resp.status_code)

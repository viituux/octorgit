from helpers_ai import structured_response
import io
import json
from pathlib import Path
import tarfile
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from octorgit.github_connection import GitHubConnection, GitHubError
from octorgit.repositories import GitHubRedirect, github_snapshot, request, safe_text
from octorgit.web import LocalServer, Jobs
from octorgit.history import HistoryStore

TOKEN = 'dummy_github_' + 'A'*24


def archive():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        data = b'import sqlite3\nsqlite3.connect("app.db")\n'
        item = tarfile.TarInfo('root/app.py'); item.size = len(data)
        tar.addfile(item, io.BytesIO(data))
    return buffer.getvalue()


class GitHubTests(unittest.TestCase):
    def test_connection_uses_only_explicit_token_and_disconnects(self):
        with patch.dict('os.environ', {'GH_TOKEN':TOKEN,'GITHUB_TOKEN':TOKEN}):
            connection = GitHubConnection()
            self.assertFalse(connection.public()['connected'])
        with patch('octorgit.github_connection.api', return_value={'login':'test-user'}) as api:
            status = connection.connect({'token':TOKEN})
        api.assert_called_once_with('/user', TOKEN)
        self.assertTrue(status['connected'])
        self.assertNotIn(TOKEN, json.dumps(status))
        self.assertEqual(connection.snapshot(), TOKEN)
        connection.disconnect()
        self.assertIsNone(connection.snapshot())

    def test_invalid_or_rejected_token_never_echoed(self):
        self.assertIsNone(safe_text(('github_pat_'+'A'*30).encode()))
        connection = GitHubConnection()
        for payload in [{}, {'token':'short'}, {'token':TOKEN+'\n'}, {'token':TOKEN,'save':True}]:
            with self.assertRaises(GitHubError): connection.connect(payload)
        failure = HTTPError('https://api.github.com/user',401,TOKEN,{},io.BytesIO(TOKEN.encode()))
        with patch('octorgit.github_connection.request', side_effect=failure):
            with self.assertRaises(GitHubError) as caught: connection.connect({'token':TOKEN})
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertFalse(connection.public()['connected'])

    def test_listing_paginated_private_repos_and_no_arbitrary_urls(self):
        connection = GitHubConnection()
        with patch('octorgit.github_connection.api', return_value={'login':'test-user'}): connection.connect({'token':TOKEN})
        rows = [{'full_name':'owner/private','private':True,'default_branch':'main','html_url':'https://evil.invalid'},
                {'full_name':'../../bad','private':False}]
        with patch('octorgit.github_connection.api', return_value=rows) as api:
            listing = connection.repositories(2)
        self.assertEqual(listing['repositories'][0]['url'], 'https://github.com/owner/private')
        self.assertTrue(listing['repositories'][0]['private'])
        self.assertEqual(len(listing['repositories']),1)
        self.assertIn('page=2',api.call_args.args[0])
        for page in [0,-1,1001,True,'2']:
            with self.assertRaises(GitHubError): connection.repositories(page)

    def test_token_is_header_only_and_redirects_are_restricted(self):
        with patch('octorgit.repositories.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(b'{}')
            request('https://api.github.com/user', 100, token=TOKEN)
            req = opener.return_value.open.call_args.args[0]
            self.assertEqual(req.get_header('Authorization'), 'Bearer '+TOKEN)
            self.assertNotIn(TOKEN, req.full_url)
        for url in ['http://api.github.com/user','https://evil.invalid/user','https://api.github.com.evil/user','https://api.github.com:443/user']:
            with self.assertRaises(ValueError): request(url,100,token=TOKEN)
        handler = GitHubRedirect()
        original = Request('https://api.github.com/repos/a/b/tarball/sha',headers={'Authorization':'Bearer '+TOKEN})
        for target in ['https://evil.invalid/archive','http://codeload.github.com/archive','https://codeload.github.com@evil.invalid/file']:
            with self.assertRaises(ValueError): handler.redirect_request(original,None,302,'',{},target)
        redirected = handler.redirect_request(original,None,302,'',{},'https://codeload.github.com/a/b/tar.gz/sha')
        self.assertEqual(redirected.get_header('Authorization'),'Bearer '+TOKEN)

    def test_authenticated_snapshot_checks_visibility_with_explicit_branch(self):
        sha = 'a'*40
        with patch('octorgit.repositories.request', side_effect=[json.dumps({'private':True,'default_branch':'main'}).encode(),json.dumps({'sha':sha}).encode(),archive()]) as call:
            repo, files, skipped = github_snapshot('https://github.com/owner/private','feature/test',token=TOKEN)
        self.assertTrue(repo['private'])
        self.assertEqual(list(files),['app.py'])
        self.assertIn('/tarball/'+sha,call.call_args_list[2].args[0])
        self.assertTrue(all(c.kwargs['token']==TOKEN for c in call.call_args_list))
        self.assertNotIn(TOKEN, json.dumps(repo))
        self.assertIn('feature%2Ftest',call.call_args_list[1].args[0])
        with patch('octorgit.repositories.request', return_value=b'{"default_branch":"main"}'):
            with self.assertRaises(ValueError): github_snapshot('https://github.com/owner/private',token=TOKEN)

    def test_private_ai_requires_separate_consent_and_token_not_persisted(self):
        class Fake:
            model = 'test-model'
            provider = 'openai-compatible'
            provider_id = 'fake'
            def generate(self, context):
                return structured_response(), {}
        with tempfile.TemporaryDirectory() as directory:
            jobs = Jobs(HistoryStore(directory))
            try:
                with patch('octorgit.github_connection.api', return_value={'login':'test-user'}): jobs.github.connect({'token':TOKEN})
                with patch('octorgit.web.create_provider',return_value=Fake()), patch('octorgit.web.github_snapshot',return_value=({'url':'https://github.com/owner/private','branch':'main','commit_sha':'a'*40,'source':'github','private':True},{'app.py':'x=1\n'},[])) as snapshot:
                    for consent in [False,True]:
                        job = jobs.submit({'source':'github','repo':'https://github.com/owner/private','use_ai':True,'private_ai_consent':consent})
                        deadline = time.monotonic()+5
                        while jobs.get(job['id'])['status'] not in ('completed','failed') and time.monotonic()<deadline: time.sleep(.01)
                        self.assertEqual(jobs.get(job['id'])['status'],'completed')
                        result = jobs.result(job['id'])
                        self.assertEqual(result['ai']['status'],'completed' if consent else 'failed')
                        self.assertNotIn(TOKEN,json.dumps(jobs.full(job['id'])))
                        self.assertIn('Repositório privado', result['documents']['README.md'])
                    self.assertEqual(snapshot.call_args.kwargs['token'],TOKEN)
                self.assertEqual(jobs.usage.summary(jobs.ai_configuration.public())['totals']['requests'],1)
            finally: jobs.close()
            for file in Path(directory).iterdir():
                if file.is_file(): self.assertNotIn(TOKEN.encode(),file.read_bytes())


class GitHubHTTPTests(unittest.TestCase):
    def test_connect_list_disconnect_and_csrf_no_token_in_get(self):
        server = LocalServer(0); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base='http://127.0.0.1:'+str(server.server_address[1])
        def get(path, payload=None, token=None):
            return urlopen(Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,
                                  headers={'Content-Type':'application/json','X-OctorGit-Token':token or server.csrf}),timeout=5)
        try:
            with self.assertRaises(HTTPError) as error: get('/api/github/connect',{'token':TOKEN},'bad')
            self.assertEqual(error.exception.code,403)
            with patch('octorgit.github_connection.api',return_value={'login':'test-user'}):
                with get('/api/github/connect',{'token':TOKEN}) as response: self.assertNotIn(TOKEN,response.read().decode())
            with get('/api/github/connection') as response: self.assertNotIn(TOKEN,response.read().decode())
            with patch('octorgit.github_connection.api',return_value=[{'full_name':'owner/private','private':True,'default_branch':'main'}]):
                with get('/api/github/repos?page=1') as response: self.assertTrue(json.load(response)['repositories'][0]['private'])
            with self.assertRaises(HTTPError): get('/api/github/repos?page=invalid')
            with get('/api/github/disconnect',{}) as response: self.assertFalse(json.load(response)['connected'])
            with self.assertRaises(HTTPError): get('/api/github/repos')
        finally: server.shutdown(); server.server_close(); thread.join(timeout=3)

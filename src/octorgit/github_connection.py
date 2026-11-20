"""Explicit GitHub connection held in RAM; never borrow the host's gh credentials."""
import json
import re
import threading
from urllib.error import HTTPError, URLError
from .repositories import request


class GitHubError(ValueError):
    pass


def api(path, token):
    try:
        return json.loads(request('https://api.github.com'+path, 1024*1024, token=token))
    except HTTPError as exc:
        messages = {401:'O GitHub não aceitou o token. Confira validade e expiração.',
                    403:'O GitHub negou acesso. Confira permissões, aprovação da organização/SSO e limite de requisições.',
                    404:'Recurso não encontrado ou sem acesso para este token.',
                    429:'Limite do GitHub atingido. Aguarde antes de tentar novamente.'}
        raise GitHubError(messages.get(exc.code, 'Não foi possível consultar o GitHub.')) from None
    except (OSError, URLError, ValueError, TypeError):
        raise GitHubError('Não foi possível conectar ao GitHub ou ler sua resposta.') from None


class GitHubConnection:
    def __init__(self):
        self.lock = threading.RLock()
        self._token = ''
        self._login = None

    def public(self):
        with self.lock:
            return {'connected':bool(self._token), 'login':self._login, 'storage':'session_memory_only'}

    def snapshot(self):
        with self.lock:
            return self._token or None

    def connect(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'token'}:
            raise GitHubError('Informe o token somente no campo de conexão do GitHub.')
        token = payload['token']
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_]{20,255}', token):
            raise GitHubError('Token GitHub inválido. Cole um token de acesso pessoal válido, sem espaços.')
        account = api('/user', token)
        login = account.get('login') if isinstance(account, dict) else None
        if not isinstance(login, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,39}', login):
            raise GitHubError('O GitHub não confirmou uma conta válida.')
        with self.lock:
            self._token, self._login = token, login
        return self.public()

    def disconnect(self):
        with self.lock:
            self._token, self._login = '', None
        return self.public()

    def repositories(self, page=1):
        if type(page) is not int or not 1 <= page <= 1000:
            raise GitHubError('Página de repositórios inválida.')
        token = self.snapshot()
        if not token:
            raise GitHubError('Conecte sua conta do GitHub antes de listar repositórios.')
        rows = api(f'/user/repos?visibility=all&affiliation=owner,collaborator,organization_member&sort=updated&per_page=20&page={page}', token)
        if not isinstance(rows, list):
            raise GitHubError('O GitHub não retornou uma lista válida de repositórios.')
        items = []
        for row in rows[:20]:
            if not isinstance(row, dict) or type(row.get("private")) is not bool:
                continue
            name = row.get('full_name')
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', name):
                continue
            branch = row.get('default_branch')
            items.append({'full_name':name, 'url':'https://github.com/'+name, 'private':row.get('private') is True,
                          'default_branch':branch if isinstance(branch, str) and len(branch)<=300 else ''})
        return {'repositories':items, 'page':page, 'has_more':len(rows)==20}

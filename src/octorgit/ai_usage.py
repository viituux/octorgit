"""Local usage ledger. No keys, prompts, responses or repository data are stored."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import sqlite3
import threading
import uuid

from .ai_engine import AIError


def profile(config):
    identity = [config['provider'], config['base_url'], config['model']]
    return {'id': hashlib.sha256(json.dumps(identity).encode()).hexdigest(),
            'provider': config['provider'], 'model': config['model']}


def amount(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise AIError('Informe um valor numérico válido, ou deixe vazio.')
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not 0 <= number <= 1000000000 or number.as_tuple().exponent < -12:
            raise ValueError()
        return str(number)
    except (InvalidOperation, ValueError):
        raise AIError('Use valores entre zero e um bilhão, com até 12 casas decimais e ponto decimal.') from None


def tokens(usage, key):
    value = usage.get(key)
    return value if type(value) is int and 0 <= value <= 10**12 else None


class UsageStore:
    def __init__(self, path=None):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path) if path else ':memory:', check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS settings (id TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)')
        self.db.commit()
        self.persistent = bool(path)

    def setting(self, key, default):
        row = self.db.execute('SELECT value FROM settings WHERE id=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def configure(self, payload, config):
        if not isinstance(payload, dict) or set(payload) != {'input_per_million', 'output_per_million', 'monthly_budget', 'paused', 'profile_id'} or type(payload['paused']) is not bool:
            raise AIError('Configuração de consumo inválida.')
        if payload['profile_id'] != profile(config)['id']:
            raise AIError('O perfil de IA mudou. Atualize o painel antes de salvar as tarifas.')
        prices = {k: amount(payload[k]) for k in ('input_per_million', 'output_per_million')}
        policy = {'monthly_budget': amount(payload['monthly_budget']), 'paused': payload['paused']}
        with self.lock, self.db:
            for key, value in [('policy', policy), ('price:'+profile(config)['id'], prices)]:
                self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
        return self.summary(config)

    def begin(self, config, purpose):
        with self.lock, self.db:
            if self.setting('policy', {}).get('paused', False):
                raise AIError('Chamadas de IA pausadas em Administração de IA. A análise estática continua disponível.')
            event = {**profile(config), 'id': uuid.uuid4().hex, 'profile_id': profile(config)['id'],
                     'created_at': datetime.now(timezone.utc).isoformat(), 'purpose': purpose,
                     'status': 'started', 'input_tokens': None, 'output_tokens': None, 'total_tokens': None,
                     'estimated_cost': None, 'currency': 'USD',
                     'prices': self.setting('price:'+profile(config)['id'], {'input_per_million': None, 'output_per_million': None})}
            self.db.execute('INSERT INTO events VALUES (?,?,?)', (event['id'], event['created_at'], json.dumps(event)))
        return event

    def finish(self, event, usage=None, failed=False):
        usage = usage if isinstance(usage, dict) else {}
        incoming = tokens(usage, 'promptTokenCount')
        outgoing = tokens(usage, 'candidatesTokenCount')
        total = tokens(usage, 'totalTokenCount')
        thoughts = tokens(usage, 'thoughtsTokenCount')
        if outgoing is not None:
            outgoing += thoughts or 0
        # Providers may include reasoning in total but omit a separate counter.
        if incoming is not None and outgoing is not None and total is not None:
            outgoing = max(outgoing, total - incoming)
        if total is None and incoming is not None and outgoing is not None:
            total = incoming + outgoing
        event.update(status='error' if failed else 'received', input_tokens=incoming, output_tokens=outgoing, total_tokens=total)
        prices = event['prices']
        if incoming is not None and outgoing is not None and all(prices[k] is not None for k in prices):
            event['estimated_cost'] = str((Decimal(incoming)*Decimal(prices['input_per_million']) + Decimal(outgoing)*Decimal(prices['output_per_million'])) / 1000000)
        with self.lock, self.db:
            self.db.execute('UPDATE events SET payload=? WHERE id=?', (json.dumps(event), event['id']))

    def summary(self, config):
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        with self.lock:
            policy = self.setting('policy', {'monthly_budget': None, 'paused': False})
            prices = self.setting('price:'+profile(config)['id'], {'input_per_million': None, 'output_per_million': None})
            monthly = [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM events WHERE created_at >= ? AND created_at < ? ORDER BY created_at DESC', (month+'-01', month+'~')).fetchall()]
            recent = [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM events ORDER BY created_at DESC LIMIT 50').fetchall()]
        subtotal = sum((Decimal(e['estimated_cost']) for e in monthly if e['estimated_cost'] is not None), Decimal(0))
        return {'currency': 'USD', 'month': month, 'timezone': 'UTC', 'profile': profile(config), 'prices': prices, 'policy': policy,
                'totals': {'requests': len(monthly), 'errors': sum(e['status']=='error' for e in monthly),
                           'input_tokens': sum(e['input_tokens'] or 0 for e in monthly), 'output_tokens': sum(e['output_tokens'] or 0 for e in monthly),
                           'total_tokens': sum(e['total_tokens'] or 0 for e in monthly), 'unknown_tokens': sum(e['total_tokens'] is None for e in monthly),
                           'unknown_costs': sum(e['estimated_cost'] is None for e in monthly), 'estimated_cost': str(subtotal),
                           'budget_reached': policy.get('monthly_budget') is not None and subtotal >= Decimal(policy['monthly_budget'])},
                'recent': recent, 'persistent': self.persistent}

    def close(self):
        with self.lock:
            self.db.close()


class MeteredProvider:
    def __init__(self, provider, store, config, purpose):
        self._provider, self.store, self.config, self.purpose = provider, store, {k: config[k] for k in ('provider','base_url','model')}, purpose
        self.model = provider.model
        self.provider = getattr(provider, 'provider', config['provider'])
        self.provider_id = getattr(provider, 'provider_id', config['provider']+':'+config['base_url'])

    def generate(self, context):
        try:
            event = self.store.begin(self.config, self.purpose)
        except sqlite3.Error:
            raise AIError('Não foi possível registrar o consumo. A chamada de IA não foi iniciada.') from None
        try:
            self._provider.last_usage = {}
            result, usage = self._provider.generate(context)
        except Exception:
            self.store.finish(event, getattr(self._provider, "last_usage", {}), failed=True)
            raise
        try:
            self.store.finish(event, usage)
        except sqlite3.Error:
            raise AIError("A chamada terminou, mas não foi possível atualizar o consumo. Consulte o provedor antes de repetir.") from None
        return result, usage

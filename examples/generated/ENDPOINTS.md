# Mapa de rotas e métodos

`scope` informa se a raiz foi selecionada ou se o prefixo permanece desconhecido. Rotas `drf_template` usam `{pk}` para o lookup padrão `[^/.]+`. HEAD/OPTIONS automáticos, API root e sufixos de formato não são enumerados. Serializer e autenticação continuam não confirmados.

- **Extraído**: `GET health/` → `views.health` (path; explicit_root).
  Evidências: `urls.py:5-5`, `views.py:6-6`.
  Não confirmado: serializer, authentication.
- **Extraído**: `GET users/` → `views.UserList` (path; explicit_root).
  Evidências: `urls.py:6-6`, `views.py:12-13`.
  Não confirmado: serializer, authentication.

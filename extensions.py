"""
Extensões Flask instanciadas fora de app.py para evitar import circular.

Os blueprints (ex.: routes/auth.py) precisam referenciar o `limiter` para
decorar rotas, mas app.py importa os blueprints. Definindo aqui e chamando
`limiter.init_app(app)` em app.py, ambos os lados importam deste módulo
neutro sem ciclo.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Rate limiter. Sem limite global por padrão — aplicamos limites pontuais
# via @limiter.limit(...) nas rotas sensíveis (login, reset de senha).
#
# Storage em memória: suficiente para um único processo. Com múltiplos
# workers gunicorn cada worker terá sua própria contagem (o limite efetivo
# fica multiplicado pelo nº de workers). Para precisão entre workers,
# trocar storage_uri por "redis://..." no futuro.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=[],
)

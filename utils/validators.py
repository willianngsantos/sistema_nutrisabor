"""
Validações de dados feitas no SERVIDOR (não confiar só no JavaScript).

Cada função recebe o valor "sujo" (como veio do form) e devolve True/False.
A normalização (tirar pontos/traços) é responsabilidade de quem valida —
ofereço helpers para isso.
"""
import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def so_digitos(valor) -> str:
    """Remove tudo que não for dígito. Aceita None."""
    return re.sub(r"\D", "", str(valor or ""))


def email_valido(email) -> bool:
    """Valida formato básico de e-mail (não verifica se existe)."""
    if not email:
        return False
    return bool(_EMAIL_RE.match(email.strip()))


def cpf_valido(cpf) -> bool:
    """Valida CPF pelos dígitos verificadores."""
    n = so_digitos(cpf)
    if len(n) != 11 or n == n[0] * 11:
        return False
    for tam in (9, 10):
        soma = sum(int(n[i]) * ((tam + 1) - i) for i in range(tam))
        dig = (soma * 10) % 11
        dig = 0 if dig == 10 else dig
        if dig != int(n[tam]):
            return False
    return True


def cnpj_valido(cnpj) -> bool:
    """Valida CNPJ pelos dígitos verificadores."""
    n = so_digitos(cnpj)
    if len(n) != 14 or n == n[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(n[i]) * pesos[i] for i in range(pos))
        resto = soma % 11
        dig = 0 if resto < 2 else 11 - resto
        if dig != int(n[pos]):
            return False
    return True

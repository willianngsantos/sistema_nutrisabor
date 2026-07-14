"""
Runner de migrações que FALHA ALTO.

Antes, o deploy.sh rodava cada script com `2>/dev/null || true`, o que engolia
erros de migração — dava pra ficar com o banco desatualizado sem ninguém saber.
Este runner roda as migrações em ordem e PARA no primeiro erro (retorno != 0 ou
marca "❌" na saída), devolvendo código de saída 1 para o deploy abortar.

Todas as migrações são idempotentes (checam INFORMATION_SCHEMA / CREATE ... IF NOT
EXISTS), então rodar sempre é seguro.

Uso: python scripts/run_migrations.py
"""
import os
import subprocess
import sys

# Ordem importa (algumas dependem de tabelas criadas por anteriores).
MIGRACOES = [
    "add_tokens_acesso.py",
    "add_feriado_cardapio.py",
    "add_editado_por_cardapio.py",
    "add_rh_tables.py",
    "add_ponto_almoco.py",
    "add_data_pagamento.py",
    "add_logo_cliente.py",
    "add_cliente_usa_sobremesa.py",
    "add_audit_log.py",
    "add_jornada_dias.py",
    "add_colab_cbo_ctps_jornada.py",
    "add_colab_dados_completos.py",
    "add_colab_dados_bancarios.py",
    "add_reajuste_beneficio.py",
    "add_rh_atestados.py",
    "add_colab_demissao.py",
    "add_empresa_assinaturas.py",
    "add_proposta_numero_unique.py",
    "limpar_precos_zerados.py",  # rotina de limpeza idempotente (não é schema)
]

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    print(f"▶ Rodando {len(MIGRACOES)} migração(ões)...\n")
    for nome in MIGRACOES:
        caminho = os.path.join(BASE, nome)
        if not os.path.exists(caminho):
            print(f"✋ Script ausente: {nome} — deploy abortado.")
            sys.exit(1)
        print(f"→ {nome}")
        r = subprocess.run([sys.executable, caminho], capture_output=True, text=True)
        saida = (r.stdout or "").strip()
        if saida:
            print("   " + saida.replace("\n", "\n   "))
        if r.stderr.strip():
            print("   [stderr] " + r.stderr.strip().replace("\n", "\n   "))
        # Falha = código != 0 OU a marca de erro que os scripts imprimem
        if r.returncode != 0 or "❌" in (r.stdout + r.stderr):
            print(f"\n✋ Migração FALHOU em '{nome}'. Deploy abortado (nada mais roda).")
            sys.exit(1)
    print("\n✅ Todas as migrações concluídas com sucesso.")


if __name__ == "__main__":
    main()

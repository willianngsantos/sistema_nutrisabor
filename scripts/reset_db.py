import mysql.connector

# Configurações do banco
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Wgs010203', # Sua senha
    'database': 'cozinha_industrial'
}

def resetar_banco():
    print("\n🚨 --- MODO DE LIMPEZA GERAL --- 🚨")
    print("Esta operação vai preparar o banco para PRODUÇÃO.")
    print("O que será apagado: Pedidos, Itens, Produtos, Clientes, Preços Negociados e Usuários extras.")
    print("O que será MANTIDO: Dados da sua Empresa (Logo, CNPJ, PIX) e o Usuário Admin (ID 1).\n")
    
    confirmacao = input("Para continuar, digite 'CONFIRMAR': ")
    
    if confirmacao != 'CONFIRMAR':
        print("❌ Operação cancelada com segurança.")
        return

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # 1. Desativa travas de segurança temporariamente
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # 2. Limpeza das tabelas transacionais (Ordem lógica)
        print("Wait... 🗑️  Limpando Itens dos Pedidos...")
        cursor.execute("TRUNCATE TABLE itens_pedido")
        
        print("Wait... 🗑️  Limpando Histórico de Pedidos...")
        cursor.execute("TRUNCATE TABLE pedidos")
        
        print("Wait... 🗑️  Limpando Tabelas de Preços Personalizados...")
        cursor.execute("TRUNCATE TABLE tabela_precos")
        
        # 3. Limpeza de Cadastros (Zera os IDs também)
        print("Wait... 🗑️  Limpando Cadastro de Produtos...")
        cursor.execute("TRUNCATE TABLE produtos")
        
        print("Wait... 🗑️  Limpando Cadastro de Clientes...")
        cursor.execute("TRUNCATE TABLE clientes")
        
        # 4. Limpeza de Usuários (Mantendo o Admin)
        print("Wait... 🗑️  Removendo usuários de teste (Preservando Admin)...")
        cursor.execute("DELETE FROM usuarios WHERE id > 1")
        # Opcional: Ajustar o auto-incremento para continuar do próximo número disponível
        cursor.execute("ALTER TABLE usuarios AUTO_INCREMENT = 2")

        # 5. Reativa travas e finaliza
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        conn.commit()
        conn.close()
        
        print("\n" + "="*50)
        print("✅ SUCESSO! O banco está limpo e pronto para uso.")
        print("🏢 Seus dados de empresa foram preservados.")
        print("👤 Seu usuário Admin (ID 1) foi preservado.")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"\n❌ Erro crítico ao resetar: {e}")

if __name__ == "__main__":
    resetar_banco()
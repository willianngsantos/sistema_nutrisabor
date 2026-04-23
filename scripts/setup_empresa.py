import mysql.connector

# Configuração do Banco (Sua senha padrão)
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Wgs010203', 
    'database': 'cozinha_industrial'
}

try:
    print("🔄 Conectando ao banco...")
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    print("🛠️ Criando tabela 'empresa'...")
    # Cria a tabela se ela não existir
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS empresa (
        id INT PRIMARY KEY,
        razao_social VARCHAR(100),
        cnpj VARCHAR(20),
        endereco VARCHAR(200),
        cidade VARCHAR(100),
        estado VARCHAR(2),
        cep VARCHAR(10),
        telefone VARCHAR(20),
        email VARCHAR(100)
    );
    """)

    # Verifica se já tem dados. Se estiver vazia, insere um padrão.
    cursor.execute("SELECT * FROM empresa")
    if not cursor.fetchone():
        print("➕ Inserindo dados iniciais...")
        cursor.execute("""
            INSERT INTO empresa (id, razao_social, cnpj, endereco, cidade, estado, cep, telefone, email)
            VALUES (1, 'NutriSabor Ltda', '00.000.000/0001-00', 'Rua Exemplo, 123', 'Taquaritinga', 'SP', '15900-000', '(16) 9999-9999', 'contato@nutrisabor.com')
        """)
    else:
        print("✅ Dados já existiam.")

    conn.commit()
    conn.close()
    print("\n🎉 SUCESSO! A tabela foi criada. Pode rodar o sistema agora.")

except Exception as e:
    print(f"\n❌ ERRO: {e}")
-- Esquema relacional do Assistente Doméstico Inteligente
-- Banco: PostgreSQL 16

CREATE TABLE IF NOT EXISTS dispositivos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    localizacao VARCHAR(100) NOT NULL,
    apelidos TEXT NOT NULL, -- palavras-chave separadas por vírgula para NLP
    bit_posicao SMALLINT NOT NULL UNIQUE CHECK (bit_posicao >= 0 AND bit_posicao <= 7),
    estado BOOLEAN NOT NULL DEFAULT FALSE,
    temperatura SMALLINT NOT NULL DEFAULT 22,
    desligar_em TIMESTAMP WITH TIME ZONE NULL,
    atualizado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS historico_comandos (
    id SERIAL PRIMARY KEY,
    origem VARCHAR(30) NOT NULL DEFAULT 'web_voz', -- web_voz, web_texto, web_manual
    texto_transcrito TEXT NOT NULL,
    comando_valido BOOLEAN NOT NULL,
    acao_interpretada VARCHAR(50),
    dispositivo_id INTEGER REFERENCES dispositivos(id) ON DELETE SET NULL,
    mascara_bits_resultante SMALLINT NOT NULL DEFAULT 0,
    mensagem_retorno TEXT NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Carga inicial dos 4 canais do Módulo Relé acionados pelas saídas do CI 7400 NAND (1Y..4Y)
INSERT INTO dispositivos (nome, localizacao, apelidos, bit_posicao, estado)
VALUES
    ('Luz do Quarto',  'Quarto',  'quarto,luz do quarto,lampada do quarto,canal 1,rele 1', 0, FALSE),
    ('Luz da Sala',    'Sala',    'sala,luz da sala,lampada da sala,canal 2,rele 2',       1, FALSE),
    ('Luz da Cozinha', 'Cozinha', 'cozinha,luz da cozinha,lampada da cozinha,canal 3,rele 3', 2, FALSE),
    ('Ar-Condicionado','Quarto',  'ar condicionado,ar-condicionado,ar,clima,climatizador,canal 4,rele 4', 3, FALSE)
ON CONFLICT (bit_posicao) DO NOTHING;

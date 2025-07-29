# Servidor P2P para Compartilhamento de Arquivos

Este é um servidor P2P (peer-to-peer) desenvolvido em Python que permite compartilhar arquivos entre usuários através de links diretos e conectar múltiplos servidores em uma rede descentralizada.

## Características

- 🔗 **Compartilhamento por Link**: Gere links diretos para seus arquivos
- 🌐 **Rede P2P**: Conecte múltiplos servidores para formar uma rede
- 📱 **Interface Web**: Interface HTML moderna e responsiva
- 🔍 **Busca Distribuída**: Encontre arquivos em toda a rede P2P
- 📊 **Estatísticas**: Acompanhe downloads e status da rede
- 🔒 **Hash SHA-256**: Verificação de integridade dos arquivos

## Instalação

1. Certifique-se de ter Python 3.7+ instalado
2. Instale as dependências:
```bash
pip install flask requests
```

## Como Usar

### Iniciar o Servidor

```bash
python servidor.py [porta]
```

Exemplos:
```bash
python servidor.py        # Usa porta padrão 5000
python servidor.py 8080   # Usa porta 8080
```

### Acessar a Interface

Abra seu navegador e acesse:
- `http://localhost:5000` (ou a porta que você escolheu)
- `http://SEU_IP:5000` (para acesso externo)

### Compartilhar Arquivos

1. **Upload**: Arraste um arquivo para a área de upload ou clique em "Escolher Arquivo"
2. **Link**: Após o upload, você receberá um link de compartilhamento
3. **Compartilhar**: Envie o link para outras pessoas baixarem o arquivo

### Conectar a Outros Peers

1. Na seção "Conectar a Peers", digite o endereço de outro servidor
2. Formato: `IP:PORTA` (exemplo: `192.168.1.100:5000`)
3. Clique em "Conectar"

Após conectar, você poderá:
- Ver arquivos de outros peers
- Baixar arquivos da rede distribuída
- Seus arquivos ficam disponíveis para outros peers

## Estrutura de Pastas

```
Servidor P2P/
├── servidor.py          # Código principal do servidor
├── shared_files/        # Pasta onde os arquivos são armazenados
└── README.md           # Este arquivo
```

## API Endpoints

### Upload de Arquivo
- **POST** `/upload`
- **Body**: FormData com arquivo

### Download de Arquivo
- **GET** `/download/<file_hash>`
- Retorna o arquivo para download

### Listar Arquivos
- **GET** `/files`
- Retorna JSON com lista de arquivos

### Conectar Peer
- **POST** `/connect_peer`
- **Body**: `{"peer_address": "IP:PORTA"}`

### Listar Peers
- **GET** `/peers`
- Retorna lista de peers conectados

## Configuração de Rede

### Para Acesso Local (mesma rede Wi-Fi)
1. Descubra seu IP local: `ipconfig` (Windows) ou `ifconfig` (Linux/Mac)
2. Inicie o servidor: `python servidor.py`
3. Compartilhe seu IP e porta com outros: `http://SEU_IP:5000`

### Para Acesso via Internet
1. Configure port forwarding no seu roteador
2. Use seu IP público
3. **Atenção**: Considere questões de segurança para uso público

## Segurança

- Arquivos são verificados com hash SHA-256
- Use apenas em redes confiáveis
- Para uso público, considere implementar autenticação
- Não compartilhe arquivos sensíveis sem criptografia adicional

## Exemplos de Uso

### Cenário 1: Compartilhar com Amigos
1. Inicie o servidor na sua máquina
2. Faça upload do arquivo
3. Envie o link de download para seus amigos

### Cenário 2: Rede de Escritório
1. Cada pessoa inicia um servidor em sua máquina
2. Conectam-se aos servidores uns dos outros
3. Todos podem acessar arquivos de toda a rede

### Cenário 3: Backup Distribuído
1. Configure múltiplos servidores
2. Arquivos ficam replicados automaticamente
3. Redundância na rede P2P

## Solução de Problemas

### Erro "Porta já em uso"
```bash
python servidor.py 8080  # Use outra porta
```

### Peer não conecta
- Verifique se o IP e porta estão corretos
- Confirme se o firewall não está bloqueando
- Teste se o peer está online: acesse `http://IP:PORTA` no navegador

### Arquivo não encontrado
- Verifique se o hash do arquivo está correto
- Confirme se o peer que tem o arquivo está online
- Recarregue a página para atualizar a lista

## Limitações

- Não há criptografia de arquivos
- Não há autenticação de usuário
- Arquivos são públicos para quem tem o link
- Dependente de conectividade de rede

## Melhorias Futuras

- [ ] Criptografia de arquivos
- [ ] Sistema de autenticação
- [ ] Interface para dispositivos móveis
- [ ] Sincronização automática
- [ ] Compressão de arquivos
- [ ] Histórico de transfers

## Licença

Este projeto é open source e pode ser usado livremente.

## Suporte

Para dúvidas ou problemas, verifique:
1. Se todas as dependências estão instaladas
2. Se a porta não está sendo usada por outro programa
3. Se o firewall não está bloqueando a conexão

import os
import hashlib
import threading
import time
from flask import Flask, request, jsonify, send_file, render_template_string, redirect
from werkzeug.utils import secure_filename
import requests
import socket

class P2PFileServer:
    def __init__(self, port=5000, upload_folder='shared_files'):
        self.app = Flask(__name__)
        self.port = port
        self.upload_folder = upload_folder
        self.shared_files = {}  # Dicionário de arquivos compartilhados
        self.server_id = self.generate_server_id()
        self.ngrok_url = None  # URL do Ngrok se disponível
        
        # Criar pasta de uploads se não existir
        if not os.path.exists(self.upload_folder):
            os.makedirs(self.upload_folder)
            
        # Tentar detectar URL do Ngrok
        self.detect_ngrok_url()
        
        # Iniciar thread para verificar Ngrok periodicamente
        self.start_ngrok_monitor()
            
        self.setup_routes()
        
    def generate_server_id(self):
        """Gerar ID único para o servidor"""
        hostname = socket.gethostname()
        timestamp = str(time.time())
        return hashlib.md5(f"{hostname}{timestamp}".encode()).hexdigest()[:8]
    
    def calculate_file_hash(self, filepath):
        """Calcular hash SHA-256 do arquivo"""
        hash_sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def detect_ngrok_url(self):
        """Detectar URL do Ngrok se estiver rodando"""
        try:
            # Tentar acessar a API local do Ngrok
            response = requests.get('http://localhost:4040/api/tunnels', timeout=3)
            if response.status_code == 200:
                data = response.json()
                tunnels = data.get('tunnels', [])
                
                for tunnel in tunnels:
                    config = tunnel.get('config', {})
                    public_url = tunnel.get('public_url', '')
                    
                    # Verificar se é o túnel para nossa porta
                    addr = config.get('addr', '')
                    if f'localhost:{self.port}' in addr or f'127.0.0.1:{self.port}' in addr:
                        self.ngrok_url = public_url
                        print(f"🌍 Ngrok detectado: {self.ngrok_url}")
                        return True
                    
                    # Fallback: pegar qualquer túnel HTTP se for porta 5000
                    if self.port == 5000 and public_url and 'http' in public_url:
                        self.ngrok_url = public_url
                        print(f"🌍 Ngrok detectado (fallback): {self.ngrok_url}")
                        return True
                        
        except Exception as e:
            print(f"Tentando detectar Ngrok: {e}")
            pass
        return False
    
    def start_ngrok_monitor(self):
        """Iniciar monitoramento do Ngrok em thread separada"""
        def monitor_ngrok():
            import time
            while True:
                try:
                    time.sleep(5)  # Verificar a cada 5 segundos
                    old_url = self.ngrok_url
                    self.detect_ngrok_url()
                    
                    # Se detectou Ngrok pela primeira vez
                    if not old_url and self.ngrok_url:
                        print(f"🎉 Ngrok conectado! Acesso público: {self.ngrok_url}")
                    elif old_url and not self.ngrok_url:
                        print("⚠️  Ngrok desconectado")
                        
                except Exception as e:
                    pass  # Ignorar erros silenciosamente
                    
        # Criar thread daemon
        monitor_thread = threading.Thread(target=monitor_ngrok, daemon=True)
        monitor_thread.start()
    
    def get_base_url(self, request_obj=None):
        """Obter URL base correto (Ngrok ou local)"""
        # Tentar detectar novamente se não tiver detectado antes
        if not self.ngrok_url:
            self.detect_ngrok_url()
            
        if self.ngrok_url:
            return self.ngrok_url
        elif request_obj:
            # Verificar se a requisição veio através do Ngrok
            host = request_obj.headers.get('Host', '')
            if 'ngrok.io' in host or 'ngrok-free.app' in host or 'ngrok.app' in host:
                scheme = 'https' if request_obj.is_secure else 'https'  # Ngrok sempre usa HTTPS
                detected_url = f"{scheme}://{host}"
                # Salvar para uso futuro
                if not self.ngrok_url:
                    self.ngrok_url = detected_url
                    print(f"🌍 Ngrok detectado via requisição: {self.ngrok_url}")
                return detected_url
        
        # Fallback para localhost
        return f"http://localhost:{self.port}"
    
    def setup_routes(self):
        """Configurar rotas da API"""
        
        @self.app.route('/')
        def index():
            """Página principal com interface web"""
            base_url = self.get_base_url(request)
            return render_template_string(HTML_TEMPLATE, 
                                        files=self.shared_files,
                                        server_id=self.server_id,
                                        base_url=base_url,
                                        ngrok_active=self.ngrok_url is not None)
        
        @self.app.route('/upload', methods=['POST'])
        def upload_file():
            """Endpoint para upload de arquivos"""
            if 'file' not in request.files:
                return jsonify({'error': 'Nenhum arquivo enviado'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'Nome de arquivo inválido'}), 400
            
            if file:
                filename = secure_filename(file.filename)
                filepath = os.path.join(self.upload_folder, filename)
                file.save(filepath)
                
                # Calcular hash e metadados do arquivo
                file_hash = self.calculate_file_hash(filepath)
                file_size = os.path.getsize(filepath)
                
                # Adicionar arquivo à lista de compartilhados
                self.shared_files[file_hash] = {
                    'filename': filename,
                    'filepath': filepath,
                    'size': file_size,
                    'hash': file_hash,
                    'upload_time': time.time(),
                    'download_count': 0
                }
                
                base_url = self.get_base_url(request)
                share_link = f"{base_url}/download/{file_hash}"
                
                return jsonify({
                    'message': 'Arquivo enviado com sucesso',
                    'file_hash': file_hash,
                    'filename': filename,
                    'share_link': share_link,
                    'ngrok_url': self.ngrok_url
                })
        
        @self.app.route('/view/<file_hash>')
        def view_file(file_hash):
            """Página de visualização do arquivo"""
            if file_hash not in self.shared_files:
                return render_template_string(FILE_NOT_FOUND_TEMPLATE), 404
            
            file_info = self.shared_files[file_hash]
            base_url = self.get_base_url(request)
            
            # Determinar tipo de arquivo para visualização
            filename = file_info['filename'].lower()
            file_type = 'unknown'
            
            if filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                file_type = 'image'
            elif filename.endswith(('.mp4', '.webm', '.ogg', '.avi', '.mov')):
                file_type = 'video'
            elif filename.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                file_type = 'audio'
            elif filename.endswith(('.pdf')):
                file_type = 'pdf'
            elif filename.endswith(('.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml')):
                file_type = 'text'
            
            return render_template_string(FILE_VIEW_TEMPLATE, 
                                        file_info=file_info,
                                        file_hash=file_hash,
                                        file_type=file_type,
                                        base_url=base_url,
                                        ngrok_active=self.ngrok_url is not None)

        @self.app.route('/download/<file_hash>')
        def download_file(file_hash):
            """Endpoint que redireciona para visualização ou faz download direto"""
            # Verificar se é uma requisição direta do navegador (não AJAX)
            user_agent = request.headers.get('User-Agent', '').lower()
            is_browser = any(browser in user_agent for browser in ['mozilla', 'chrome', 'safari', 'edge', 'firefox'])
            
            # Se for requisição de navegador e não tiver parâmetro 'direct', redirecionar para visualização
            if is_browser and not request.args.get('direct'):
                return redirect(f'/view/{file_hash}')
            
            # Caso contrário, fazer download direto
            if file_hash not in self.shared_files:
                return jsonify({'error': 'Arquivo não encontrado'}), 404
            
            file_info = self.shared_files[file_hash]
            file_info['download_count'] += 1
            
            return send_file(file_info['filepath'], 
                           as_attachment=True, 
                           download_name=file_info['filename'])
        
        @self.app.route('/preview/<file_hash>')
        def preview_file(file_hash):
            """Endpoint para preview direto do arquivo (para imagens, vídeos, etc.)"""
            if file_hash not in self.shared_files:
                return jsonify({'error': 'Arquivo não encontrado'}), 404
            
            file_info = self.shared_files[file_hash]
            return send_file(file_info['filepath'], 
                           as_attachment=False)
        
        @self.app.route('/files')
        def list_files():
            """Listar todos os arquivos disponíveis"""
            files_list = []
            base_url = self.get_base_url(request)
            for file_hash, info in self.shared_files.items():
                files_list.append({
                    'hash': file_hash,
                    'filename': info['filename'],
                    'size': info['size'],
                    'download_count': info['download_count'],
                    'share_link': f"{base_url}/download/{file_hash}"
                })
            return jsonify(files_list)
        
        @self.app.route('/refresh_ngrok')
        def refresh_ngrok():
            """Atualizar detecção do Ngrok"""
            old_url = self.ngrok_url
            self.detect_ngrok_url()
            return jsonify({
                'old_url': old_url,
                'new_url': self.ngrok_url,
                'ngrok_active': self.ngrok_url is not None,
                'message': 'Ngrok detectado!' if self.ngrok_url else 'Ngrok não encontrado'
            })
        
        @self.app.route('/status')
        def get_status():
            """Obter status completo do servidor"""
            return jsonify({
                'server_id': self.server_id,
                'port': self.port,
                'ngrok_url': self.ngrok_url,
                'ngrok_active': self.ngrok_url is not None,
                'file_count': len(self.shared_files)
            })
        
        @self.app.route('/debug_ngrok')
        def debug_ngrok():
            """Debug da detecção do Ngrok"""
            try:
                response = requests.get('http://localhost:4040/api/tunnels', timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    return jsonify({
                        'ngrok_api_working': True,
                        'tunnels_data': data,
                        'current_ngrok_url': self.ngrok_url,
                        'port_looking_for': self.port
                    })
                else:
                    return jsonify({
                        'ngrok_api_working': False,
                        'status_code': response.status_code,
                        'current_ngrok_url': self.ngrok_url
                    })
            except Exception as e:
                return jsonify({
                    'ngrok_api_working': False,
                    'error': str(e),
                    'current_ngrok_url': self.ngrok_url
                })
        
        @self.app.route('/get_link/<file_hash>')
        def get_file_link(file_hash):
            """Obter link correto para um arquivo específico"""
            if file_hash not in self.shared_files:
                return jsonify({'error': 'Arquivo não encontrado'}), 404
            
            base_url = self.get_base_url(request)
            file_info = self.shared_files[file_hash]
            
            return jsonify({
                'file_hash': file_hash,
                'filename': file_info['filename'],
                'download_link': f"{base_url}/download/{file_hash}",
                'base_url': base_url,
                'ngrok_active': self.ngrok_url is not None,
                'link_type': 'mundial' if self.ngrok_url else 'local'
            })
    
    def start_server(self):
        """Iniciar servidor"""
        print(f"Iniciando servidor P2P na porta {self.port}")
        print(f"ID do servidor: {self.server_id}")
        print(f"Pasta de arquivos: {self.upload_folder}")
        print(f"Acesse: http://localhost:{self.port}")
        
        if self.ngrok_url:
            print(f"🌍 Acesso público: {self.ngrok_url}")
        else:
            print("💡 Para acesso público, execute: criar_link_publico.bat")
        
        self.app.run(host='0.0.0.0', port=self.port, debug=False)

# Template HTML para interface web
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Servidor P2P - Compartilhamento de Arquivos</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(45deg, #4CAF50, #2196F3);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .server-info {
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-top: 20px;
            flex-wrap: wrap;
        }

        .info-card {
            background: rgba(255, 255, 255, 0.2);
            padding: 15px 25px;
            border-radius: 10px;
            text-align: center;
        }

        .content {
            padding: 40px;
        }

        .section {
            margin-bottom: 40px;
        }

        .section h2 {
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #4CAF50;
            display: inline-block;
        }

        .upload-area {
            border: 3px dashed #4CAF50;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            background: #f8f9fa;
            transition: all 0.3s ease;
        }

        .upload-area:hover {
            background: #e8f5e8;
            border-color: #2196F3;
        }

        .upload-area input[type="file"] {
            display: none;
        }

        .upload-btn {
            display: inline-block;
            padding: 15px 30px;
            background: #4CAF50;
            color: white;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s ease;
            text-decoration: none;
        }

        .upload-btn:hover {
            background: #45a049;
            transform: translateY(-2px);
        }

        .submit-btn {
            background: #2196F3;
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 20px;
            transition: all 0.3s ease;
        }

        .submit-btn:hover {
            background: #1976D2;
            transform: translateY(-2px);
        }

        .files-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }

        .file-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
        }

        .file-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
        }

        .file-name {
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
            word-break: break-word;
        }

        .file-info {
            color: #666;
            font-size: 14px;
            margin-bottom: 15px;
        }

        .download-link {
            display: inline-block;
            padding: 8px 15px;
            background: #4CAF50;
            color: white;
            text-decoration: none;
            border-radius: 15px;
            transition: all 0.3s ease;
            margin-right: 5px;
            margin-bottom: 5px;
            font-size: 13px;
            min-width: 70px;
            text-align: center;
        }

        .download-link:hover {
            background: #45a049;
            transform: scale(1.05);
        }

        .copy-btn {
            padding: 8px 15px;
            background: #FF9800;
            color: white;
            border: none;
            border-radius: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-right: 5px;
            margin-bottom: 5px;
            font-size: 13px;
            min-width: 70px;
        }

        .copy-btn:hover {
            background: #F57C00;
        }

        .file-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            align-items: center;
        }

        .no-files {
            text-align: center;
            color: #666;
            font-style: italic;
            padding: 40px;
        }

        .status-message {
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: center;
        }

        .success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        @media (max-width: 768px) {
            .header h1 {
                font-size: 2em;
            }

            .server-info {
                gap: 15px;
            }

            .content {
                padding: 20px;
            }

            .files-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔗 Servidor P2P</h1>
            <p>Compartilhamento Descentralizado de Arquivos</p>
            {% if ngrok_active %}
            <div style="background: rgba(76, 175, 80, 0.2); padding: 10px; border-radius: 10px; margin-top: 15px;">
                <strong>🌍 ACESSO MUNDIAL ATIVO</strong><br>
                <small>Servidor acessível via Ngrok em qualquer lugar do mundo!</small>
            </div>
            {% else %}
            <div style="background: rgba(255, 152, 0, 0.2); padding: 10px; border-radius: 10px; margin-top: 15px;">
                <strong>🏠 ACESSO LOCAL</strong><br>
                <small>Execute criar_link_publico.bat para acesso mundial</small>
            </div>
            {% endif %}
            <div class="server-info">
                <div class="info-card">
                    <strong>ID do Servidor</strong><br>
                    {{ server_id }}
                </div>
                <div class="info-card">
                    <strong>Arquivos Compartilhados</strong><br>
                    {{ files|length }}
                </div>
                {% if ngrok_active %}
                <div class="info-card" style="background: rgba(76, 175, 80, 0.3);">
                    <strong>🌍 Status</strong><br>
                    Online Mundial
                </div>
                {% endif %}
            </div>
        </div>

        <div class="content">
            <!-- Seção de Upload -->
            <div class="section">
                <h2>📤 Enviar Arquivo</h2>
                <form id="uploadForm" enctype="multipart/form-data">
                    <div class="upload-area">
                        <p style="margin-bottom: 20px; font-size: 18px;">
                            Arraste um arquivo aqui ou clique para selecionar
                        </p>
                        <label for="fileInput" class="upload-btn">
                            Escolher Arquivo
                        </label>
                        <input type="file" id="fileInput" name="file" required>
                        <p id="fileName" style="margin-top: 15px; color: #666;"></p>
                        <button type="submit" class="submit-btn" id="uploadBtn" style="display: none;">
                            Enviar Arquivo
                        </button>
                    </div>
                </form>
                <div id="uploadStatus"></div>
            </div>

            <!-- Seção de Arquivos Compartilhados -->
            <div class="section">
                <h2>📁 Arquivos Disponíveis</h2>
                {% if files %}
                    <div class="files-grid">
                        {% for hash, file in files.items() %}
                        <div class="file-card">
                            <div class="file-name">{{ file.filename }}</div>
                            <div class="file-info">
                                Tamanho: {{ "%.2f"|format(file.size / 1024 / 1024) }} MB<br>
                                Downloads: {{ file.download_count }}<br>
                                Hash: {{ hash[:16] }}...<br>
                            </div>
                            <div class="file-actions">
                                <a href="/view/{{ hash }}" class="download-link" style="background: #2196F3;">
                                    Visualizar
                                </a>
                                <a href="/download/{{ hash }}" class="download-link">
                                    Baixar
                                </a>
                                <button class="copy-btn" onclick="copyLinkDynamic('{{ hash }}')">
                                    Copiar Link
                                </button>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <div class="no-files">
                        Nenhum arquivo compartilhado ainda. Envie um arquivo para começar!
                    </div>
                {% endif %}
            </div>
        </div>
    </div>

    <script>
        // Upload de arquivo
        document.getElementById('fileInput').addEventListener('change', function(e) {
            const fileName = e.target.files[0]?.name;
            if (fileName) {
                document.getElementById('fileName').textContent = `Arquivo selecionado: ${fileName}`;
                document.getElementById('uploadBtn').style.display = 'inline-block';
            }
        });

        document.getElementById('uploadForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData();
            const fileInput = document.getElementById('fileInput');
            const file = fileInput.files[0];
            
            if (!file) {
                showMessage('Selecione um arquivo para enviar.', 'error');
                return;
            }
            
            formData.append('file', file);
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    const linkType = result.ngrok_url ? '🌍 Link Mundial' : '🏠 Link Local';
                    showMessage(`Arquivo enviado com sucesso! ${linkType}: ${result.share_link}`, 'success');
                    fileInput.value = '';
                    document.getElementById('fileName').textContent = '';
                    document.getElementById('uploadBtn').style.display = 'none';
                    setTimeout(() => location.reload(), 2000);
                } else {
                    showMessage(result.error || 'Erro ao enviar arquivo.', 'error');
                }
            } catch (error) {
                showMessage('Erro de conexão. Tente novamente.', 'error');
            }
        });

        // Copiar link do arquivo
        function copyLink(fileHash) {
            // Usar a URL base correta (Ngrok se disponível, senão localhost)
            const baseUrl = '{{ base_url }}';
            const link = `${baseUrl}/download/${fileHash}`;
            navigator.clipboard.writeText(link).then(() => {
                const linkType = baseUrl.includes('ngrok') ? '🌍 Link Mundial' : '🏠 Link Local';
                alert(`${linkType} copiado para a área de transferência!\n${link}`);
            }).catch(() => {
                // Fallback para navegadores antigos
                prompt('Copie este link:', link);
            });
        }

        // Mostrar mensagens de status
        function showMessage(message, type) {
            const statusDiv = document.getElementById('uploadStatus');
            statusDiv.innerHTML = `<div class="status-message ${type}">${message}</div>`;
            setTimeout(() => {
                statusDiv.innerHTML = '';
            }, 5000);
        }

        // Drag and drop
        const uploadArea = document.querySelector('.upload-area');
        
        uploadArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            uploadArea.style.backgroundColor = '#e8f5e8';
        });
        
        uploadArea.addEventListener('dragleave', function(e) {
            e.preventDefault();
            uploadArea.style.backgroundColor = '#f8f9fa';
        });
        
        uploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            uploadArea.style.backgroundColor = '#f8f9fa';
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                document.getElementById('fileInput').files = files;
                document.getElementById('fileName').textContent = `Arquivo selecionado: ${files[0].name}`;
                document.getElementById('uploadBtn').style.display = 'inline-block';
            }
        });

        // Verificar status do Ngrok periodicamente
        function checkNgrokStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    // Atualizar interface se necessário
                    if (data.ngrok_active && !window.ngrokWasActive) {
                        console.log('Ngrok detectado! Recarregando página...');
                        setTimeout(() => location.reload(), 1000);
                    }
                    
                    // Atualizar URL base global para JavaScript
                    if (data.ngrok_url) {
                        window.currentBaseUrl = data.ngrok_url;
                    } else {
                        window.currentBaseUrl = 'http://localhost:5000';
                    }
                    
                    window.ngrokWasActive = data.ngrok_active;
                })
                .catch(error => {
                    console.log('Erro ao verificar status:', error);
                });
        }

        // Função melhorada para copiar link usando URL dinâmica
        function copyLinkDynamic(fileHash) {
            const baseUrl = window.currentBaseUrl || '{{ base_url }}';
            const link = `${baseUrl}/download/${fileHash}`;
            
            navigator.clipboard.writeText(link).then(() => {
                const linkType = baseUrl.includes('ngrok') ? '🌍 Link Mundial' : '🏠 Link Local';
                alert(`${linkType} copiado!\n${link}\n\n💡 Este link direciona para visualização primeiro!`);
            }).catch(() => {
                prompt('Copie este link:', link);
            });
        }

        // Inicializar URL base
        window.currentBaseUrl = '{{ base_url }}';

        // Verificar Ngrok a cada 10 segundos
        window.ngrokWasActive = {{ 'true' if ngrok_active else 'false' }};
        setInterval(checkNgrokStatus, 10000);

        // Verificar imediatamente após 5 segundos (caso Ngrok tenha acabado de iniciar)
        setTimeout(checkNgrokStatus, 5000);
    </script>
</body>
</html>
'''

# Template HTML para visualização de arquivos
FILE_VIEW_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visualizar: {{ file_info.filename }} - Servidor P2P</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(45deg, #4CAF50, #2196F3);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2em;
            margin-bottom: 10px;
        }

        .content {
            padding: 40px;
        }

        .file-info {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
        }

        .file-info h2 {
            color: #333;
            margin-bottom: 15px;
        }

        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }

        .info-item {
            background: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }

        .info-item strong {
            display: block;
            color: #666;
            font-size: 14px;
            margin-bottom: 5px;
        }

        .info-item span {
            color: #333;
            font-size: 16px;
        }

        .preview-area {
            background: white;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            margin-bottom: 30px;
            min-height: 300px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .preview-content {
            max-width: 100%;
            max-height: 70vh;
        }

        .preview-content img {
            max-width: 100%;
            max-height: 70vh;
            border-radius: 8px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
        }

        .preview-content video,
        .preview-content audio {
            max-width: 100%;
            border-radius: 8px;
        }

        .text-preview {
            background: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            text-align: left;
            font-family: 'Courier New', monospace;
            white-space: pre-wrap;
            overflow-x: auto;
            max-height: 400px;
            overflow-y: auto;
        }

        .unsupported-preview {
            color: #666;
            font-style: italic;
        }

        .action-buttons {
            display: flex;
            gap: 15px;
            justify-content: center;
            flex-wrap: wrap;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 25px;
            font-size: 16px;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .btn-download {
            background: #4CAF50;
            color: white;
        }

        .btn-download:hover {
            background: #45a049;
            transform: translateY(-2px);
        }

        .btn-back {
            background: #6c757d;
            color: white;
        }

        .btn-back:hover {
            background: #5a6268;
            transform: translateY(-2px);
        }

        .btn-copy {
            background: #FF9800;
            color: white;
        }

        .btn-copy:hover {
            background: #F57C00;
        }

        @media (max-width: 768px) {
            .container {
                margin: 10px;
            }

            .content {
                padding: 20px;
            }

            .action-buttons {
                flex-direction: column;
                align-items: center;
            }

            .btn {
                width: 100%;
                max-width: 300px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Visualizar Arquivo</h1>
            <p>{{ file_info.filename }}</p>
        </div>

        <div class="content">
            <div class="file-info">
                <h2>ℹ️ Informações do Arquivo</h2>
                <div class="info-grid">
                    <div class="info-item">
                        <strong>Nome do Arquivo</strong>
                        <span>{{ file_info.filename }}</span>
                    </div>
                    <div class="info-item">
                        <strong>Tamanho</strong>
                        <span>{{ "%.2f"|format(file_info.size / 1024 / 1024) }} MB</span>
                    </div>
                    <div class="info-item">
                        <strong>Downloads</strong>
                        <span>{{ file_info.download_count }}</span>
                    </div>
                    <div class="info-item">
                        <strong>Hash</strong>
                        <span>{{ file_hash[:16] }}...</span>
                    </div>
                </div>
            </div>

            <div class="preview-area">
                <div class="preview-content">
                    {% if file_type == 'image' %}
                        <img src="/preview/{{ file_hash }}" alt="{{ file_info.filename }}" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div class="unsupported-preview" style="display: none;">
                            <h3>🖼️ Imagem</h3>
                            <p>Não foi possível carregar a prévia da imagem.</p>
                        </div>
                    {% elif file_type == 'video' %}
                        <video controls>
                            <source src="/preview/{{ file_hash }}" type="video/{{ file_info.filename.split('.')[-1] }}">
                            Seu navegador não suporta reprodução de vídeo.
                        </video>
                    {% elif file_type == 'audio' %}
                        <audio controls style="width: 100%;">
                            <source src="/preview/{{ file_hash }}" type="audio/{{ file_info.filename.split('.')[-1] }}">
                            Seu navegador não suporta reprodução de áudio.
                        </audio>
                    {% elif file_type == 'pdf' %}
                        <div class="unsupported-preview">
                            <h3>📄 Documento PDF</h3>
                            <p>Clique em "Baixar" para visualizar o PDF.</p>
                        </div>
                    {% elif file_type == 'text' %}
                        <div id="textPreview" class="text-preview">
                            Carregando conteúdo do texto...
                        </div>
                    {% else %}
                        <div class="unsupported-preview">
                            <h3>📎 {{ file_info.filename.split('.')[-1].upper() }} File</h3>
                            <p>Tipo de arquivo não suportado para visualização.<br>
                            Clique em "Baixar" para obter o arquivo.</p>
                        </div>
                    {% endif %}
                </div>
            </div>

            <div class="action-buttons">
                <a href="/download/{{ file_hash }}?direct=1" class="btn btn-download">
                    ⬇️ Baixar Arquivo
                </a>
                <button onclick="copyViewLink()" class="btn btn-copy">
                    {% if ngrok_active %}
                    🌍 Copiar Link de Visualização
                    {% else %}
                    📋 Copiar Link de Visualização
                    {% endif %}
                </button>
                <button onclick="copyDirectLink()" class="btn btn-copy" style="background: #9C27B0;">
                    {% if ngrok_active %}
                    🔗 Copiar Link de Download
                    {% else %}
                    🔗 Copiar Link de Download
                    {% endif %}
                </button>
                <a href="/" class="btn btn-back">
                    ← Voltar ao Início
                </a>
            </div>
        </div>
    </div>

    <script>
        // Copiar link de visualização
        function copyViewLink() {
            const baseUrl = '{{ base_url }}';
            const link = `${baseUrl}/view/{{ file_hash }}`;
            navigator.clipboard.writeText(link).then(() => {
                const linkType = baseUrl.includes('ngrok') ? '🌍 Link Mundial' : '🏠 Link Local';
                alert(`${linkType} de visualização copiado!\n${link}`);
            }).catch(() => {
                prompt('Copie este link de visualização:', link);
            });
        }

        // Copiar link de download direto
        function copyDirectLink() {
            const baseUrl = '{{ base_url }}';
            const link = `${baseUrl}/download/{{ file_hash }}`;
            navigator.clipboard.writeText(link).then(() => {
                const linkType = baseUrl.includes('ngrok') ? '🌍 Link Mundial' : '🏠 Link Local';
                alert(`${linkType} de download copiado!\n${link}\n\nEste link redireciona para visualização primeiro.`);
            }).catch(() => {
                prompt('Copie este link de download:', link);
            });
        }

        // Carregar conteúdo de texto se for arquivo de texto
        {% if file_type == 'text' %}
        fetch('/preview/{{ file_hash }}')
            .then(response => response.text())
            .then(text => {
                const preview = document.getElementById('textPreview');
                // Limitar tamanho do texto para visualização
                const maxLength = 5000;
                if (text.length > maxLength) {
                    preview.textContent = text.substring(0, maxLength) + '\n\n... (arquivo truncado para visualização)';
                } else {
                    preview.textContent = text;
                }
            })
            .catch(error => {
                document.getElementById('textPreview').textContent = 'Erro ao carregar conteúdo do arquivo.';
            });
        {% endif %}
    </script>
</body>
</html>
'''

# Template para arquivo não encontrado
FILE_NOT_FOUND_TEMPLATE = '''
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arquivo Não Encontrado - Servidor P2P</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            padding: 20px;
        }

        .error-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 50px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            max-width: 500px;
        }

        .error-icon {
            font-size: 4em;
            margin-bottom: 20px;
        }

        .error-title {
            color: #333;
            font-size: 2em;
            margin-bottom: 15px;
        }

        .error-message {
            color: #666;
            font-size: 1.2em;
            margin-bottom: 30px;
            line-height: 1.5;
        }

        .btn-back {
            background: #4CAF50;
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 25px;
            font-size: 16px;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
        }

        .btn-back:hover {
            background: #45a049;
            transform: translateY(-2px);
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-icon">📁❌</div>
        <h1 class="error-title">Arquivo Não Encontrado</h1>
        <p class="error-message">
            O arquivo que você está procurando não foi encontrado no servidor ou na rede P2P.
        </p>
        <a href="/" class="btn-back">← Voltar ao Início</a>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    import sys
    
    # Porta padrão ou especificada via argumento
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    
    # Criar e iniciar servidor
    server = P2PFileServer(port=port)
    server.start_server()
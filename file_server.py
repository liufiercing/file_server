from flask import Flask, send_file, jsonify, render_template_string, request
import os
from pathlib import Path
import logging
import zipfile
import tempfile
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import threading
import queue
import time
import subprocess

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# 添加全局变量来跟踪打包进度
zip_progress = {}
zip_progress_lock = Lock()

@app.before_request
def log_request_info():
    app.logger.debug('Headers: %s', request.headers)
    app.logger.debug('Body: %s', request.get_data())

@app.after_request
def log_response_info(response):
    """只记录非文件下载的响应"""
    if not response.direct_passthrough:  # 如果不是文件下载响应
        app.logger.debug('Response: %s', response.get_data())
    return response

# 设置共享的根目录
SHARE_DIR = "/mnt/seismic"

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>文件下载服务</title>
    <meta charset="utf-8">
    <!-- 添加 Font Awesome CSS -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <!-- 添加 highlight.js 支持 -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
    <!-- 添加更多语言支持 -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/go.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/python.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/languages/java.min.js"></script>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 40px auto;
            max-width: 800px;
            padding: 0 20px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        a {
            color: #0066cc;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        .folder {
            color: #e67e22;
        }
        .file {
            color: #7f8c8d;
        }
        .download-btn {
            color: #27ae60;
            padding: 4px 8px;
            border-radius: 4px;
            transition: color 0.3s;
        }
        .download-btn:hover {
            color: #219a52;
        }
        .breadcrumb {
            margin-bottom: 20px;
            padding: 8px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }
        .breadcrumb a {
            margin: 0 5px;
        }
        .home-icon {
            color: #3498db;
        }
        /* 添加图片预览相关样式 */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.9);
        }
        
        .modal-content {
            margin: auto;
            display: block;
            max-width: 90%;
            max-height: 90%;
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
        }
        
        .close {
            position: absolute;
            right: 25px;
            top: 10px;
            color: #f1f1f1;
            font-size: 40px;
            font-weight: bold;
            cursor: pointer;
        }
        
        .preview-btn {
            color: #3498db;
            padding: 4px 8px;
            margin-right: 10px;
            border-radius: 4px;
            transition: color 0.3s;
        }
        
        .preview-btn:hover {
            color: #2980b9;
        }
        
        /* 添加左右切换按钮样式 */
        .nav-btn {
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            color: white;
            font-size: 30px;
            cursor: pointer;
            padding: 15px;
            background-color: rgba(0, 0, 0, 0.5);
            border-radius: 5px;
            transition: 0.3s;
        }
        
        .nav-btn:hover {
            background-color: rgba(0, 0, 0, 0.8);
        }
        
        .prev {
            left: 20px;
        }
        
        .next {
            right: 20px;
        }
        
        /* 图片信息样式 */
        .image-info {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background-color: rgba(0, 0, 0, 0.7);
            color: white;
            padding: 15px;
            text-align: center;
            font-size: 14px;
        }
        
        /* 修改模态框内容样式 */
        .modal-container {
            position: relative;
            width: 100%;
            height: 100%;
        }
        
        /* 添加代码预览相关样式 */
        .code-modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.9);
        }
        
        .code-container {
            position: relative;
            width: 90%;
            height: 90%;
            margin: 2% auto;
            background-color: #fff;
            border-radius: 5px;
            padding: 20px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        
        .code-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }
        
        .code-header .close {
            margin-left: 20px;
            font-size: 24px;
            color: #666;
        }
        
        .code-header .buttons {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .code-content {
            flex: 1;
            overflow: auto;
            background-color: #f8f9fa;
            border-radius: 4px;
            position: relative;
        }
        
        .code-content pre {
            margin: 0;
            padding: 15px;
        }
        
        .code-content code {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
            font-size: 14px;
            line-height: 1.5;
        }
        
        .code-btn {
            color: #3498db;
            padding: 6px 12px;
            border-radius: 4px;
            transition: all 0.3s;
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
        }
        
        .code-btn:hover {
            color: #2980b9;
            background-color: #e9ecef;
        }
    </style>
</head>
<body>
    <h1><i class="fas fa-server"></i> 文件下载列表</h1>
    <div class="breadcrumb">
        <a href="/"><i class="fas fa-home home-icon"></i> 根目录</a>
        {% for part in breadcrumbs %}
            / <a href="{{ part.url }}">{{ part.name }}</a>
        {% endfor %}
    </div>
    <table>
        <tr>
            <th>名称</th>
            <th>大小</th>
            <th>修改时间</th>
            <th>操作</th>
        </tr>
        {% if current_path != '' %}
        <tr>
            <td><a href="{{ parent_url }}"><i class="fas fa-level-up-alt"></i> 返回上级</a></td>
            <td>-</td>
            <td>-</td>
            <td>-</td>
        </tr>
        {% endif %}
        {% for item in items %}
        <tr>
            <td>
                {% if item.is_dir %}
                    <i class="fas fa-folder folder"></i>
                    <a href="{{ item.url }}">{{ item.name }}</a>
                {% else %}
                    <i class="fas fa-{% if item.is_image %}image{% else %}file{% endif %} file"></i>
                    {{ item.name }}
                {% endif %}
            </td>
            <td>{{ item.size if not item.is_dir else '-' }}</td>
            <td>{{ item.mtime }}</td>
            <td>
                {% if item.is_image %}
                    <a href="#" class="preview-btn" onclick="previewImage('{{ item.download_url }}')">
                        <i class="fas fa-eye"></i> 预览
                    </a>
                {% elif item.is_code %}
                    <a href="#" class="preview-btn" onclick="previewCode('{{ item.download_url }}', '{{ item.name }}')">
                        <i class="fas fa-code"></i> 预览
                    </a>
                {% endif %}
                <a href="{{ item.download_url }}" class="download-btn">
                    <i class="fas fa-download"></i> 下载
                </a>
            </td>
        </tr>
        {% endfor %}
    </table>

    <!-- 修改图片预览模态框 -->
    <div id="imageModal" class="modal">
        <span class="close" onclick="closeModal()">&times;</span>
        <div class="modal-container">
            <div class="nav-btn prev" onclick="navigateImage(-1)">
                <i class="fas fa-chevron-left"></i>
            </div>
            <img class="modal-content" id="previewImg">
            <div class="nav-btn next" onclick="navigateImage(1)">
                <i class="fas fa-chevron-right"></i>
            </div>
            <div class="image-info" id="imageInfo"></div>
        </div>
    </div>

    <!-- 添加代码预览模态框 -->
    <div id="codeModal" class="code-modal">
        <div class="code-container">
            <div class="code-header">
                <span id="codeFileName"></span>
                <div class="buttons">
                    <a href="#" class="code-btn" id="copyCodeBtn">
                        <i class="fas fa-copy"></i> 复制代码
                    </a>
                    <span class="close" onclick="closeCodeModal()">&times;</span>
                </div>
            </div>
            <div class="code-content">
                <pre><code id="codeContent"></code></pre>
            </div>
        </div>
    </div>

    <!-- 修改 JavaScript 部分 -->
    <script>
        var modal = document.getElementById("imageModal");
        var modalImg = document.getElementById("previewImg");
        var imageInfo = document.getElementById("imageInfo");
        var currentImageIndex = 0;
        var imageItems = [];

        // 初始化图片列表
        function initImageList() {
            imageItems = Array.from(document.querySelectorAll('tr')).filter(row => {
                return row.querySelector('.fa-image') !== null;
            }).map(row => {
                return {
                    url: row.querySelector('.preview-btn').getAttribute('onclick').match(/'([^']+)'/)[1],
                    name: row.querySelector('td:first-child').textContent.trim(),
                    size: row.querySelector('td:nth-child(2)').textContent.trim(),
                    time: row.querySelector('td:nth-child(3)').textContent.trim()
                };
            });
        }

        function previewImage(url) {
            initImageList();
            currentImageIndex = imageItems.findIndex(item => item.url === url);
            showCurrentImage();
            modal.style.display = "block";
        }

        function showCurrentImage() {
            const currentImage = imageItems[currentImageIndex];
            modalImg.src = currentImage.url;
            imageInfo.innerHTML = `
                <div>${currentImage.name}</div>
                <div>大小: ${currentImage.size} | 修改时间: ${currentImage.time}</div>
                <div>${currentImageIndex + 1} / ${imageItems.length}</div>
            `;
        }

        function navigateImage(direction) {
            currentImageIndex = (currentImageIndex + direction + imageItems.length) % imageItems.length;
            showCurrentImage();
        }

        function closeModal() {
            modal.style.display = "none";
        }

        // 点击模态框外部关闭
        modal.onclick = function(e) {
            if (e.target === modal) {
                closeModal();
            }
        }

        // 键盘控制
        document.addEventListener('keydown', function(e) {
            if (modal.style.display === "block") {
                switch(e.key) {
                    case 'Escape':
                        closeModal();
                        break;
                    case 'ArrowLeft':
                        navigateImage(-1);
                        break;
                    case 'ArrowRight':
                        navigateImage(1);
                        break;
                }
            }
        });

        var codeModal = document.getElementById("codeModal");
        var codeContent = document.getElementById("codeContent");
        var codeFileName = document.getElementById("codeFileName");
        var copyCodeBtn = document.getElementById("copyCodeBtn");

        async function previewCode(url, filename) {
            try {
                const response = await fetch(url);
                const text = await response.text();
                
                codeContent.textContent = text;
                codeFileName.textContent = filename;
                
                // 应用代码高亮
                hljs.highlightElement(codeContent);
                
                codeModal.style.display = "block";
            } catch (error) {
                console.error('Error loading code:', error);
                alert('加载文件失败');
            }
        }

        function closeCodeModal() {
            codeModal.style.display = "none";
        }

        // 修改复制代码功能
        copyCodeBtn.onclick = async function(e) {
            e.preventDefault();  // 阻止默认行为
            
            try {
                const codeText = codeContent.textContent || codeContent.innerText;
                await navigator.clipboard.writeText(codeText);
                
                // 临时改变按钮文字显示复制成功
                const originalText = copyCodeBtn.innerHTML;
                copyCodeBtn.innerHTML = '<i class="fas fa-check"></i> 已复制';
                copyCodeBtn.style.color = '#27ae60';  // 变成绿色
                
                // 2秒后恢复原样
                setTimeout(() => {
                    copyCodeBtn.innerHTML = originalText;
                    copyCodeBtn.style.color = '';
                }, 2000);
            } catch (err) {
                console.error('复制失败:', err);
                
                // 显示复制失败
                const originalText = copyCodeBtn.innerHTML;
                copyCodeBtn.innerHTML = '<i class="fas fa-times"></i> 复制失败';
                copyCodeBtn.style.color = '#e74c3c';  // 变成红色
                
                // 2秒后恢复原样
                setTimeout(() => {
                    copyCodeBtn.innerHTML = originalText;
                    copyCodeBtn.style.color = '';
                }, 2000);
            }
            return false;
        };

        // 为了兼容性，添加一个后备的复制方法
        function fallbackCopyTextToClipboard(text) {
            const textArea = document.createElement("textarea");
            textArea.value = text;
            
            // 将文本域添加到文档中
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            textArea.style.top = "-999999px";
            document.body.appendChild(textArea);
            
            // 选择文本并复制
            textArea.focus();
            textArea.select();
            
            try {
                document.execCommand('copy');
                return true;
            } catch (err) {
                console.error('Fallback: 复制失败', err);
                return false;
            } finally {
                document.body.removeChild(textArea);
            }
        }

        // 如果浏览器不支持 navigator.clipboard，使用后备方法
        if (!navigator.clipboard) {
            copyCodeBtn.onclick = function(e) {
                e.preventDefault();
                const codeText = codeContent.textContent || codeContent.innerText;
                const success = fallbackCopyTextToClipboard(codeText);
                
                // 显示复制结果
                const originalText = copyCodeBtn.innerHTML;
                if (success) {
                    copyCodeBtn.innerHTML = '<i class="fas fa-check"></i> 已复制';
                    copyCodeBtn.style.color = '#27ae60';
                } else {
                    copyCodeBtn.innerHTML = '<i class="fas fa-times"></i> 复制失败';
                    copyCodeBtn.style.color = '#e74c3c';
                }
                
                // 2秒后恢复原样
                setTimeout(() => {
                    copyCodeBtn.innerHTML = originalText;
                    copyCodeBtn.style.color = '';
                }, 2000);
                
                return false;
            };
        }

        // 点击模态框外部关闭
        codeModal.onclick = function(e) {
            if (e.target === codeModal) {
                closeCodeModal();
            }
        }

        // ESC键关闭代码预览
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && codeModal.style.display === "block") {
                closeCodeModal();
            }
        });
    </script>
</body>
</html>
"""

def get_human_size(size_in_bytes):
    """将字节转换为人类可读的格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} PB"

def get_file_time(timestamp):
    """将时间戳转换为可读格式"""
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

def is_image_file(filename):
    """检查文件是否为图片"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    return os.path.splitext(filename.lower())[1] in image_extensions

def is_code_file(filename):
    """检查文件是否为代码文件"""
    code_extensions = {
        '.py', '.java', '.js', '.cpp', '.c', '.h', '.css', '.html', 
        '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.ts', '.sh',
        '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.conf',
        '.sql', '.md', '.txt'  # 包含一些文本文件
    }
    return os.path.splitext(filename.lower())[1] in code_extensions

@app.route('/')
@app.route('/<path:subpath>')
def index(subpath=''):
    """显示文件列表页面"""
    # 构建当前完整路径
    current_dir = os.path.join(SHARE_DIR, subpath)
    
    # 安全检查
    if not os.path.commonpath([os.path.abspath(current_dir), SHARE_DIR]) == SHARE_DIR:
        return "访问被拒绝", 403
    
    if not os.path.exists(current_dir):
        return "目录不存在", 404

    # 生成面包屑导航
    breadcrumbs = []
    path_parts = subpath.split('/') if subpath else []
    current_path = ''
    for part in path_parts:
        if part:
            current_path = os.path.join(current_path, part)
            breadcrumbs.append({
                'name': part,
                'url': f'/{current_path}'
            })

    # 获取父目录URL
    parent_url = '/' + os.path.dirname(subpath) if subpath else '/'

    # 获取目录内容
    items = []
    try:
        for name in sorted(os.listdir(current_dir)):
            full_path = os.path.join(current_dir, name)
            relative_path = os.path.relpath(full_path, SHARE_DIR)
            is_dir = os.path.isdir(full_path)
            stat = os.stat(full_path)
            
            item = {
                'name': name,
                'is_dir': is_dir,
                'is_image': not is_dir and is_image_file(name),
                'is_code': not is_dir and is_code_file(name),  # 添加代码文件判断
                'url': f'/{relative_path}' if is_dir else None,
                'size': get_human_size(stat.st_size) if not is_dir else None,
                'mtime': get_file_time(stat.st_mtime),
                'download_url': f'/api/download/{relative_path}'
            }
            items.append(item)
        
        # 排序：目录在前，文件在后
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

    except Exception as e:
        return f"Error: {str(e)}", 500

    return render_template_string(
        HTML_TEMPLATE,
        items=items,
        current_path=subpath,
        breadcrumbs=breadcrumbs,
        parent_url=parent_url
    )

def create_zip_file(folder_path, base_path):
    """使用tar命令创建文件夹的打包文件"""
    app.logger.debug(f"开始打包文件夹: {folder_path}")
    temp_dir = tempfile.mkdtemp()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_filename = f'folder_{timestamp}.tar'
    archive_path = os.path.join(temp_dir, archive_filename)
    
    # 创建任务ID
    task_id = str(int(time.time() * 1000))
    
    try:
        # 获取文件夹大小作为进度参考
        total_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, _, filenames in os.walk(folder_path)
                        for filename in filenames)
        
        # 初始化进度信息
        with zip_progress_lock:
            zip_progress[task_id] = {
                'total_files': 0,
                'processed_files': 0,
                'total_size': total_size,
                'processed_size': 0,
                'status': 'processing'
            }
        
        try:
            # 使用tar命令打包文件夹，不压缩
            process = subprocess.Popen(
                ['tar', '-cf', archive_path, '.'],
                cwd=folder_path,  # 直接在目标文件夹中执行命令
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 监控打包进度
            while True:
                if process.poll() is not None:
                    break
                    
                if os.path.exists(archive_path):
                    current_size = os.path.getsize(archive_path)
                    with zip_progress_lock:
                        zip_progress[task_id]['processed_size'] = current_size
                        # 使用打包文件大小比例估算进度
                        progress_percent = (current_size / total_size) if total_size > 0 else 0
                        zip_progress[task_id]['processed_files'] = int(progress_percent * 100)
                
                time.sleep(0.1)
            
            # 检查打包结果
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                error_message = stderr.decode() if stderr else "未知错误"
                raise Exception(f"打包失败: {error_message}")
            
        except Exception as e:
            app.logger.error(f"打包过程出错: {str(e)}")
            raise
            
        with zip_progress_lock:
            zip_progress[task_id]['status'] = 'completed'
            zip_progress[task_id]['processed_files'] = 100
            zip_progress[task_id]['processed_size'] = total_size
        
        app.logger.debug(f"打包完成: {archive_path}")
        return archive_path, task_id
        
    except Exception as e:
        app.logger.error(f"创建打包文件失败: {str(e)}")
        with zip_progress_lock:
            if task_id in zip_progress:
                zip_progress[task_id]['status'] = 'failed'
        if os.path.exists(archive_path):
            os.remove(archive_path)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise e

# 添加进度查询接口
@app.route('/api/zip-progress/<task_id>')
def get_zip_progress(task_id):
    """获取压缩进度"""
    with zip_progress_lock:
        if task_id not in zip_progress:
            return jsonify({'error': '任务不存在'}), 404
        
        progress = zip_progress[task_id].copy()
        if progress['status'] == 'completed':
            # 清理进度信息
            del zip_progress[task_id]
        
        return jsonify({
            'total_files': progress['total_files'],
            'processed_files': progress['processed_files'],
            'total_size': progress['total_size'],
            'processed_size': progress['processed_size'],
            'status': progress['status'],
            'percent': (progress['processed_size'] / progress['total_size'] * 100) if progress['total_size'] > 0 else 0
        })

@app.route('/api/download/<path:filepath>', methods=['GET'])
def download_file(filepath):
    """下载指定文件或文件夹"""
    full_path = None
    zip_path = None
    
    try:
        full_path = os.path.join(SHARE_DIR, filepath)
        app.logger.debug(f"请求下载: {full_path}")
        
        if not os.path.exists(full_path):
            app.logger.error(f"文件不存在: {full_path}")
            return jsonify({'error': '文件或目录不存在'}), 404
            
        if not os.path.commonpath([os.path.abspath(full_path), SHARE_DIR]) == SHARE_DIR:
            app.logger.error(f"无效的访问路径: {full_path}")
            return jsonify({'error': '无效的文件路径'}), 403
        
        if os.path.isfile(full_path):
            app.logger.debug("开始文件下载")
            filename = os.path.basename(full_path)
            return send_file(
                full_path,
                as_attachment=True,
                download_name=filename
            )
        elif os.path.isdir(full_path):
            app.logger.debug("开始文件夹打包下载")
            archive_path, task_id = create_zip_file(full_path, os.path.dirname(full_path))
            
            if not os.path.exists(archive_path):
                raise Exception("打包文件创建失败")
                
            dirname = os.path.basename(full_path)
            app.logger.debug(f"发送打包文件: {archive_path}")
            return send_file(
                archive_path,
                as_attachment=True,
                download_name=f'{dirname}.tar',
                mimetype='application/x-tar'
            )
    except Exception as e:
        app.logger.error(f"下载处理出错: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if zip_path and os.path.exists(zip_path):
            temp_dir = os.path.dirname(zip_path)
            try:
                os.remove(zip_path)
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                app.logger.debug("临时文件清理完成")
            except Exception as e:
                app.logger.error(f"清理临时文件失败: {str(e)}")

if __name__ == '__main__':
    print("Starting server on port 8090...")
    print(f"Sharing directory: {SHARE_DIR}")
    print("Debug mode: ON")
    app.run(host='0.0.0.0', port=8088, debug=True) 
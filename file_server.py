from flask import Flask, send_file, jsonify, render_template_string, request
import os
from pathlib import Path
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

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
SHARE_DIR = "/path/to/your/directory"

# HTML模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>文件下载服务</title>
    <meta charset="utf-8">
    <!-- 添加 Font Awesome CSS -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
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
                    <i class="fas fa-file file"></i>
                    {{ item.name }}
                {% endif %}
            </td>
            <td>{{ item.size if not item.is_dir else '-' }}</td>
            <td>{{ item.mtime }}</td>
            <td>
                {% if not item.is_dir %}
                    <a href="{{ item.download_url }}" class="download-btn">
                        <i class="fas fa-download"></i> 下载
                    </a>
                {% else %}
                    -
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
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
                'url': f'/{relative_path}' if is_dir else None,
                'size': get_human_size(stat.st_size) if not is_dir else None,
                'mtime': get_file_time(stat.st_mtime),  # 添加修改时间
                'download_url': f'/api/download/{relative_path}' if not is_dir else None
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

@app.route('/api/download/<path:filepath>', methods=['GET'])
def download_file(filepath):
    """下载指定文件"""
    try:
        full_path = os.path.join(SHARE_DIR, filepath)
        # 检查路径是否在允许的目录下
        if not os.path.commonpath([os.path.abspath(full_path), SHARE_DIR]) == SHARE_DIR:
            return jsonify({'error': '无效的文件路径'}), 403
        
        if os.path.isfile(full_path):
            # 获取文件名
            filename = os.path.basename(full_path)
            return send_file(
                full_path,
                as_attachment=True,
                download_name=filename  # 确保下载时使用原始文件名
            )
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        app.logger.error(f"下载文件时出错: {str(e)}")  # 添加错误日志
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting server on port 8088...")
    print(f"Sharing directory: {SHARE_DIR}")
    print("Debug mode: ON")
    app.run(host='0.0.0.0', port=8088, debug=True) 
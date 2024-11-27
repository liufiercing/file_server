# 文件下载服务器

一个基于 Flask 的简单文件下载服务器，提供 Web 界面和 API 接口。

## 功能特点

- 📁 文件目录浏览
- 📥 文件下载
- 🔍 目录导航
- 📊 文件信息显示（大小、修改时间）
- 🎯 简洁美观的界面
- 🛡️ 基本的安全保护

## 安装依赖 

## 使用方法

1. 修改配置（如需要）：
   ```python
   SHARE_DIR = "/path/to/your/directory"  # 修改为您要共享的目录路径
   ```

2. 运行服务器：
   ```bash
   python file_server.py
   ```

3. 访问服务：
   - Web 界面：`http://your-server:8088`
   - API 接口：
     - 获取文件列表：`GET http://your-server:8088/api/files`
     - 下载文件：`GET http://your-server:8088/api/download/path/to/file`

## 安全说明

- 仅支持文件下载，不支持上传
- 包含路径遍历防护
- 建议在生产环境中：
  - 配置 HTTPS
  - 添加访问认证
  - 使用反向代理（如 Nginx）

## API 接口

### 下载文件
- 请求：`GET /api/download/<filepath>`
- 响应：文件内容或错误信息
- 示例：`/api/download/example.txt`

## 界面功能

- 文件大小显示
- 修改时间显示
- 目录层级导航
- 文件下载按钮
- 响应式设计

## 注意事项

1. 默认端口为 8088
2. 调试模式默认开启
3. 支持所有文件类型的下载
4. 自动过滤非共享目录的访问

## 开发环境

- Python 3.x
- Flask
- Font Awesome（用于图标显示）

## 许可证

MIT License
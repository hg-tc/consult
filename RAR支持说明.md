# RAR文件支持说明

## ✅ 已添加RAR文件支持

系统现已支持上传和解压 `.rar` 格式文件！

---

## 🔧 所需依赖

### Python库

需要安装 `rarfile` 库：

```bash
pip install rarfile
```

### 系统工具（Linux）

还需要安装系统级别的 `unrar` 工具：

**Ubuntu/Debian:**
```bash
sudo apt-get install unrar
```

**CentOS/RHEL:**
```bash
sudo yum install unrar
```

**或者通过EPEL仓库:**
```bash
sudo yum install epel-release
sudo yum install unrar
```

---

## 📦 支持的归档格式

系统现在支持以下归档格式：

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| ZIP | `.zip` | 标准ZIP格式 |
| RAR | `.rar` | RAR压缩格式 |

### 功能特性

- ✅ 自动识别ZIP或RAR格式
- ✅ 解压归档文件
- ✅ 并行处理其中的多个文档
- ✅ 支持的工作区文档和全局数据库
- ✅ 自动清理临时文件

---

## 🚀 使用方法

### 1. 上传RAR到全局数据库

```bash
curl -X POST http://localhost:18000/api/database/upload \
  -F "file=@documents.rar"
```

### 2. 上传RAR到工作区

```bash
curl -X POST http://localhost:18000/api/workspaces/1/documents/upload \
  -F "file=@project_docs.rar"
```

### 3. 上传ZIP到全局数据库

```bash
curl -X POST http://localhost:18000/api/database/upload \
  -F "file=@documents.zip"
```

---

## 📁 修改的文件

### 1. `backend/app/services/zip_processor.py`

**新增内容:**
- 导入 `rarfile` 库
- 添加 `extract_archive()` 方法（统一入口）
- 添加 `extract_rar()` 方法（解压RAR文件）
- 添加 `ARCHIVE_EXTENSIONS` 常量

**关键代码:**
```python
async def extract_archive(archive_path: str, extract_to: str) -> List[Dict]:
    """解压归档文件（ZIP或RAR）"""
    file_ext = Path(archive_path).suffix.lower()
    
    if file_ext == '.zip':
        return await ZipProcessor.extract_zip(archive_path,ものを extract_to)
    elif file_ext == '.rar':
        return await ZipProcessor.extract_rar(archive_path, extract_to)
    else:
        raise ValueError(f"不支持的归档格式: {file_ext}")
```

### 2. `backend/app_simple.py`

**修改内容:**
- 第203行: 添加 `.rar` 到允许的文件类型
- 第254行: 检测归档文件（.zip 或 .rar）
- 第1266行: 使用 `extract_archive()` 代替 `extract_zip()`
- 第2105行: 在工作区上传中也支持RAR

---

## ⚠️ 注意事项

### 1. 依赖检查

如果未安装 `rarfile` 库或 `unrar` 工具，系统会显示友好错误提示：

```
ValueError: rarfile库未安装，无法处理RAR文件。
请运行: pip install rarfile
```

或

```
ValueError: RAR解压失败：需要安装unrar工具
```

### 2. 文件大小限制

继承现有的文件大小限制：
- 单个归档文件: 50MB
- 解压后的文件: 每个50MB以内

### 3. RAR版本支持

支持标准RAR格式（RAR 2.0及更高版本），不支持RAR5格式。

---

## 🧪 测试建议

### 测试场景

1. **正常RAR文件**
   ```bash
   # 创建测试RAR文件
   rar a test.rar file1.pdf file2.docx
   
   # 上传测试
   curl -X POST http://localhost:18000/api/database/upload \
     -F "file=@test.rar"
   ```

2. **混合格式**
   - 上传包含多个文档的RAR文件
   - 验证所有文件都被正确处理

3. **错误处理**
   - 测试损坏的RAR文件
   - 测试未安装依赖的情况

---

## 🎯 功能对比

| 特性 | ZIP支持 | RAR支持 |
|------|---------|---------|
| 文件扩展名 | `.zip` | `.rar` |
| Python库 | `zipfile` (内置) | `rarfile` (需安装) |
| 系统工具 | 不需要 | 需要unrar |
| 性能 | 优秀 | 良好 |
| 兼容性 | 优秀 | 良好 |

---

## 📝 开发说明

### 扩展新格式

如果需要支持更多归档格式（如 `.7z`, `.tar.gz`），可以：

1. 在 `ZipProcessor` 中添加新的解压方法
2. 在 `extract_archive()` 中添加新的分支
3. 在 `app_simple.py` 中添加文件扩展名

**示例:**
```python
elif file_ext == '.7z':
    return await ZipProcessor.extract_7z(archive_path, extract_to)
```

---

## 🐛 故障排除

### 问题1: 无法解压RAR文件

**错误信息:** `RAR解压失败：需要安装unrar工具`

**解决方案:**
```bash
# Ubuntu/Debian
sudo apt-get install unrar

# CentOS/RHEL
sudo yum install unrar
```

### 问题2: Python库未安装

**错误信息:** `rarfile库未安装，无法处理RAR文件`

**解决方案:**
```bash
# 在虚拟环境中安装
cd backend
source venv/bin/activate
pip install rarfile
```

### 问题3: 文件太大

**错误信息:** `文件大小超过限制`

**解决方案:**
修改 `backend/app_simple.py` 中的文件大小限制（第212行）。

---

## 🎉 总结

现在系统支持两种归档格式：
- ✅ ZIP格式（.zip）- 无需额外依赖
- ✅ RAR格式（.rar）- 需要安装rarfile和unrar

用户可以根据需要选择任意一种格式上传批量文档！🚀

"""
工作区文档管理器
为工作区文档提供JSON存储，类似于全局文档管理器
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# 工作区数据目录
WORKSPACE_DATA_DIR = Path("/root/consult/backend/workspace_data")
WORKSPACE_DATA_DIR.mkdir(exist_ok=True)


def get_workspace_documents_file(workspace_id: str) -> Path:
    """获取工作区文档JSON文件路径"""
    return WORKSPACE_DATA_DIR / f"workspace_{workspace_id}_documents.json"


def load_workspace_documents(workspace_id: str) -> List[Dict[str, Any]]:
    """从文件加载工作区文档"""
    file_path = get_workspace_documents_file(workspace_id)
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载工作区文档失败: {e}")
    return []


def save_workspace_documents(workspace_id: str, documents: List[Dict[str, Any]]):
    """保存工作区文档到文件"""
    try:
        file_path = get_workspace_documents_file(workspace_id)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存工作区文档失败: {e}")


def add_workspace_document(workspace_id: str, document_data: Dict[str, Any]) -> bool:
    """添加文档到工作区JSON记录"""
    try:
        documents = load_workspace_documents(workspace_id)
        documents.append(document_data)
        save_workspace_documents(workspace_id, documents)
        logger.info(f"工作区 {workspace_id} 添加文档记录: {document_data.get('original_filename')}")
        return True
    except Exception as e:
        logger.error(f"添加工作区文档记录失败: {e}")
        return False


def update_workspace_document_status(workspace_id: str, doc_id: str, status: str, **kwargs):
    """更新工作区文档状态"""
    try:
        documents = load_workspace_documents(workspace_id)
        for doc in documents:
            if doc.get('id') == doc_id:
                doc['status'] = status
                for key, value in kwargs.items():
                    doc[key] = value
                break
        save_workspace_documents(workspace_id, documents)
        logger.info(f"工作区 {workspace_id} 文档状态已更新: {doc_id} -> {status}")
    except Exception as e:
        logger.error(f"更新工作区文档状态失败: {str(e)}")


def delete_workspace_document(workspace_id: str, doc_id: str) -> bool:
    """从工作区JSON中删除文档记录"""
    try:
        documents = load_workspace_documents(workspace_id)
        documents = [doc for doc in documents if doc.get('id') != doc_id]
        save_workspace_documents(workspace_id, documents)
        logger.info(f"工作区 {workspace_id} 删除文档记录: {doc_id}")
        return True
    except Exception as e:
        logger.error(f"删除工作区文档记录失败: {e}")
        return False


def delete_workspace_document_by_filename(workspace_id: str, filename: str) -> int:
    """通过文件名从工作区JSON中删除文档记录（返回删除数量）"""
    try:
        documents = load_workspace_documents(workspace_id)
        before_count = len(documents)
        documents = [doc for doc in documents if doc.get('original_filename') != filename]
        after_count = len(documents)
        deleted_count = before_count - after_count
        
        if deleted_count > 0:
            save_workspace_documents(workspace_id, documents)
            logger.info(f"工作区 {workspace_id} 通过文件名删除文档: {filename}, 删除 {deleted_count} 条记录")
        
        return deleted_count
    except Exception as e:
        logger.error(f"通过文件名删除工作区文档记录失败: {e}")
        return 0


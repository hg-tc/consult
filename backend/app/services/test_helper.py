#!/usr/bin/env python3
"""
测试辅助工具
提供各种测试功能的辅助函数
"""

import asyncio
import json
import time
import requests
import websocket
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class TestHelper:
    """测试辅助工具类"""
    
    def __init__(self, base_url: str = "http://localhost:18000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30
    
    def upload_document(self, file_path: str, workspace_id: str = "1") -> Dict[str, Any]:
        """上传文档"""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {'workspace_id': workspace_id}
                
                response = self.session.post(
                    f"{self.base_url}/api/agent/upload-document",
                    files=files,
                    data=data
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"success": False, "error": f"HTTP {response.status_code}"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def upload_global_document(self, file_path: str) -> Dict[str, Any]:
        """上传文档到全局数据库"""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                
                response = self.session.post(
                    f"{self.base_url}/api/global/documents",
                    files=files
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"success": False, "error": f"HTTP {response.status_code}"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def ask_question(self, question: str, workspace_id: str = "1", history: List[Dict] = None) -> Dict[str, Any]:
        """发送问题"""
        try:
            data = {
                "message": question,
                "workspace_id": workspace_id,
                "history": history or []
            }
            
            response = self.session.post(
                f"{self.base_url}/api/agent/chat",
                json=data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def search_global(self, query: str, workspace_id: str = "1") -> Dict[str, Any]:
        """全局搜索"""
        try:
            data = {
                "query": query,
                "workspace_id": workspace_id
            }
            
            response = self.session.post(
                f"{self.base_url}/api/global/search",
                json=data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_workspace(self, name: str) -> Dict[str, Any]:
        """创建工作区"""
        try:
            data = {"name": name}
            
            response = self.session.post(
                f"{self.base_url}/api/workspaces",
                json=data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_workspace_documents(self, workspace_id: str) -> Dict[str, Any]:
        """获取工作区文档列表"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/workspaces/{workspace_id}/documents"
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_global_documents(self) -> Dict[str, Any]:
        """获取全局文档列表"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/global/documents"
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete_document(self, doc_id: str, workspace_id: str = None) -> Dict[str, Any]:
        """删除文档"""
        try:
            if workspace_id:
                # 删除工作区文档
                response = self.session.delete(
                    f"{self.base_url}/api/workspaces/{workspace_id}/documents/{doc_id}"
                )
            else:
                # 删除全局文档
                response = self.session.delete(
                    f"{self.base_url}/api/global/documents/{doc_id}"
                )
            
            if response.status_code == 200:
                return {"success": True}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def download_document(self, doc_id: str, workspace_id: str = None) -> Dict[str, Any]:
        """下载文档"""
        try:
            if workspace_id:
                # 下载工作区文档
                url = f"{self.base_url}/api/workspaces/{workspace_id}/documents/{doc_id}/download"
            else:
                # 下载全局文档
                url = f"{self.base_url}/api/global/documents/{doc_id}/download"
            
            response = self.session.get(url)
            
            if response.status_code == 200:
                return {"success": True, "content": response.content}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def preview_document(self, doc_id: str, workspace_id: str = None) -> Dict[str, Any]:
        """预览文档"""
        try:
            if workspace_id:
                # 预览工作区文档
                url = f"{self.base_url}/api/workspaces/{workspace_id}/documents/{doc_id}/preview"
            else:
                # 预览全局文档
                url = f"{self.base_url}/api/global/documents/{doc_id}/preview"
            
            response = self.session.get(url)
            
            if response.status_code == 200:
                return {"success": True, "content": response.text}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def test_websocket_connection(self, url: str = "ws://localhost:18000/ws/status") -> Dict[str, Any]:
        """测试WebSocket连接"""
        try:
            ws = websocket.create_connection(url, timeout=10)
            
            # 发送测试消息
            test_message = {"type": "ping", "data": "test"}
            ws.send(json.dumps(test_message))
            
            # 接收响应
            response = ws.recv()
            ws.close()
            
            return {
                "success": True,
                "response": response,
                "latency": 0.1  # 模拟延迟
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def measure_response_time(self, func, *args, **kwargs) -> tuple:
        """测量函数执行时间"""
        start_time = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start_time
        return result, duration
    
    def evaluate_answer_quality(self, question: str, answer: str) -> float:
        """评估答案质量（简单版本）"""
        if not answer or len(answer.strip()) < 10:
            return 0.0
        
        # 简单的质量评估指标
        score = 0.0
        
        # 长度评分（0-2分）
        length_score = min(len(answer) / 200, 2.0)
        score += length_score
        
        # 关键词匹配评分（0-2分）
        question_words = set(question.lower().split())
        answer_words = set(answer.lower().split())
        keyword_score = len(question_words.intersection(answer_words)) / len(question_words) * 2
        score += keyword_score
        
        # 结构评分（0-1分）
        if any(marker in answer for marker in ['1.', '2.', '3.', '首先', '其次', '最后']):
            score += 1.0
        
        return min(score, 5.0)  # 最高5分
    
    def check_document_content(self, file_path: str) -> Dict[str, Any]:
        """检查文档内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "success": True,
                "file_size": len(content),
                "line_count": len(content.split('\n')),
                "word_count": len(content.split()),
                "has_content": len(content.strip()) > 0
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def generate_test_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成测试报告"""
        total_tests = len(results)
        passed = len([r for r in results if r.get('success', False)])
        failed = total_tests - passed
        
        avg_response_time = sum(r.get('duration', 0) for r in results) / total_tests if total_tests > 0 else 0
        
        return {
            "summary": {
                "total_tests": total_tests,
                "passed": passed,
                "failed": failed,
                "success_rate": passed / total_tests if total_tests > 0 else 0,
                "avg_response_time": avg_response_time
            },
            "details": results
        }

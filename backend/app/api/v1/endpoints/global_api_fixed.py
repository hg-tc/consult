"""
修复后的全局文档列表API - 只从JSON读取，不查询向量数据库
"""
# 从第536行到第618行替换

def list_global_documents_fixed():
    """列出所有全局文档（只从JSON文件，快速返回）"""
    try:
        # 只从JSON文件加载（快速，不会超时）
        documents = load_global_documents()
        
        # 如果文件为空或没有记录，返回空列表
        if not documents:
            logger.info("全局文档文件为空，返回空列表")
            return {
                "documents": [],
                "total_count": 0,
                "message": "暂无全局文档"
            }
        
        # 转换格式
        result_documents = []
        for doc in documents:
            result_documents.append({
                "id": doc.get('id', ''),
                "filename": doc.get('filename', ''),
                "original_filename": doc.get('original_filename', ''),
                "file_size": doc.get('file_size', 0),
                "file_type": doc.get('file_type', ''),
                "status": doc.get('status', 'completed'),
                "created_at": doc.get('created_at', ''),
                "chunk_count": doc.get('chunk_count', 0),
                "is_archive": doc.get('is_archive', False),
                "task_id": doc.get('task_id')
            })
        
        return {
            "documents": result_documents,
            "total_count": len(result_documents),
            "message": "全局文档列表"
        }
    except Exception as e:
        logger.error(f"获取全局文档列表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


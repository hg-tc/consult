"""
文档生成端点
"""

import json
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.document_generator import DocumentGenerator

logger = logging.getLogger(__name__)
router = APIRouter()
generator = DocumentGenerator()


@router.post("/from-template")
async def generate_from_template(
    template_id: int,
    data: str = Form(...),  # JSON字符串格式的数据
    output_format: str = Form("docx"),
    workspace_id: int = Form(1),  # 暂时固定工作区ID
    db: AsyncSession = Depends(get_db)
):
    """
    基于模板生成文档

    - **template_id**: 模板ID
    - **data**: JSON格式的填充数据
    - **output_format**: 输出格式 (docx, pdf, pptx)
    - **workspace_id**: 工作区ID
    """
    try:
        # 解析数据
        template_data = json.loads(data)

        # 获取模板信息（暂时跳过数据库查询）
        template_path = f"templates/template_{template_id}.docx"  # 假设模板路径

        # 验证模板数据
        validation = generator.validate_template_data(template_path, template_data)
        if not validation['valid']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"模板数据验证失败，缺少变量: {validation['missing_variables']}"
            )

        # 生成文档
        output_path = generator.generate_from_template(
            template_path,
            template_data,
            output_format
        )

        return {
            "message": "文档生成成功",
            "output_path": output_path,
            "output_format": output_format,
            "validation": validation
        }

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的JSON数据格式"
        )
    except Exception as e:
        logger.error(f"文档生成失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文档生成失败: {str(e)}"
        )


@router.post("/from-data")
async def generate_from_data(
    template_type: str = Form("report"),
    data: str = Form(...),  # JSON字符串格式的数据
    output_format: str = Form("docx"),
    workspace_id: int = Form(1),  # 暂时固定工作区ID
    db: AsyncSession = Depends(get_db)
):
    """
    根据数据生成文档（不基于模板）

    - **template_type**: 模板类型 (report, contract等)
    - **data**: JSON格式的文档数据
    - **output_format**: 输出格式 (docx, pdf, pptx)
    - **workspace_id**: 工作区ID
    """
    try:
        # 解析数据
        document_data = json.loads(data)

        # 生成文档
        output_path = generator.create_document_from_data(
            document_data,
            template_type,
            output_format
        )

        return {
            "message": "文档生成成功",
            "output_path": output_path,
            "output_format": output_format,
            "template_type": template_type
        }

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的JSON数据格式"
        )
    except Exception as e:
        logger.error(f"文档生成失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文档生成失败: {str(e)}"
        )


@router.get("/supported-formats")
async def get_supported_formats():
    """获取支持的文档格式"""
    return {
        "formats": generator.get_supported_formats()
    }


@router.post("/validate-template")
async def validate_template_data(
    template_id: int,
    data: str = Form(...),  # JSON字符串格式的数据
    db: AsyncSession = Depends(get_db)
):
    """
    验证模板数据

    - **template_id**: 模板ID
    - **data**: JSON格式的数据
    """
    try:
        # 解析数据
        template_data = json.loads(data)

        # 获取模板信息（暂时跳过数据库查询）
        template_path = f"templates/template_{template_id}.docx"  # 假设模板路径

        # 验证数据
        validation = generator.validate_template_data(template_path, template_data)

        return {
            "valid": validation['valid'],
            "missing_variables": validation['missing_variables'],
            "extra_variables": validation['extra_variables'],
            "required_variables": validation['required_variables']
        }

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的JSON数据格式"
        )
    except Exception as e:
        logger.error(f"模板验证失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"模板验证失败: {str(e)}"
        )


@router.get("/download/{filename}")
async def download_generated_document(filename: str):
    """下载生成的文件"""
    file_path = generator.output_dir / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream"
    )

"""
模板模型
"""

from sqlalchemy import Column, String, Text, Integer, ForeignKey, DateTime, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base, BaseModel


class Template(BaseModel):
    """模板表"""
    __tablename__ = "templates"

    name = Column(String, nullable=False)
    description = Column(Text)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)

    # 模板类型
    template_type = Column(String, nullable=False)  # word, pdf, pptx等
    category = Column(String)  # 分类标签

    # 模板元数据
    variables = Column(JSON)  # 可填充的变量列表
    preview_image = Column(String)  # 预览图片路径

    # 使用统计
    usage_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # 所属用户
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 关系
    owner = relationship("User", back_populates="templates")

    def __repr__(self):
        return f"<Template(id={self.id}, name={self.name}, template_type={self.template_type})>"

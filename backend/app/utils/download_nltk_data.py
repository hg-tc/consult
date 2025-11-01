#!/usr/bin/env python3
"""
NLTK 数据下载脚本
用于在联网环境中预先下载 NLTK 所需的资源
"""
import os
import sys
from pathlib import Path

def download_nltk_data():
    """下载 NLTK 必需的数据包"""
    try:
        import nltk
        
        # 设置下载目录
        nltk_data_dir = os.getenv('NLTK_DATA', os.path.expanduser('~/nltk_data'))
        nltk_data_path = Path(nltk_data_dir)
        nltk_data_path.mkdir(parents=True, exist_ok=True)
        
        # 设置 NLTK 数据路径
        nltk.data.path.insert(0, str(nltk_data_path))
        os.environ['NLTK_DATA'] = str(nltk_data_path)
        
        print(f"📥 开始下载 NLTK 数据到: {nltk_data_path}")
        
        # 需要下载的资源列表
        resources = [
            'punkt',           # 分词器（必需）
            'punkt_tab',       # punkt 表格数据（punkt 的依赖）
            'stopwords',       # 停用词（可选，但常用）
            'averaged_perceptron_tagger',  # 词性标注（可选）
        ]
        
        for resource in resources:
            try:
                print(f"  检查 {resource}...")
                nltk.data.find(f'tokenizers/{resource}')
                print(f"  ✅ {resource} 已存在")
            except LookupError:
                try:
                    print(f"  ⬇️  下载 {resource}...")
                    nltk.download(resource, download_dir=str(nltk_data_path), quiet=False)
                    print(f"  ✅ {resource} 下载完成")
                except Exception as e:
                    print(f"  ❌ {resource} 下载失败: {e}")
                    if resource == 'punkt':
                        print(f"  ⚠️  punkt 是必需的，请重试")
                        return False
        
        print(f"\n✅ NLTK 数据下载完成！")
        print(f"数据目录: {nltk_data_path}")
        print(f"\n提示：可以设置环境变量 NLTK_DATA={nltk_data_path} 来指定数据路径")
        return True
        
    except ImportError:
        print("❌ NLTK 未安装，请先安装: pip install nltk")
        return False
    except Exception as e:
        print(f"❌ 下载过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = download_nltk_data()
    sys.exit(0 if success else 1)


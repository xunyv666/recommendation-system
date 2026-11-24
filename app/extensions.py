"""Flask 扩展单例。

拆成独立模块，避免 app 工厂与 models 之间循环导入。
"""
from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

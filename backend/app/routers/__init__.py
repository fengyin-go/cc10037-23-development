"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import business, quality_reference, resource

# quality_reference 使用 /api/quality 静态前缀，必须排在含 /api/{module} 的
# resource 之前，否则会被动态段抢走。
ROUTERS = [business, quality_reference, resource]

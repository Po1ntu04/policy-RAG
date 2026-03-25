"""
政务指标管理模块

提供完整的指标抽取、存储、审计、导出功能。
"""

from private_gpt.server.indicators.models import (
    Indicator,
    IndicatorBatch,
    IndicatorQuery,
    AuditRequest,
    AuditResult,
    CompletionStatus,
    ConfidenceLevel,
    EvidenceLocation,
)
from private_gpt.server.indicators.indicator_store import IndicatorStore
from private_gpt.server.indicators.indicator_service import IndicatorService
from private_gpt.server.indicators.indicators_router import indicators_router
from private_gpt.server.indicators.prompts import (
    get_qa_prompt,
    get_extraction_prompt,
    get_table_prompt,
    get_audit_prompt,
    SYSTEM_PROMPT_SMART_QA,
    SYSTEM_PROMPT_INDICATOR_EXTRACTION,
    SYSTEM_PROMPT_TABLE_GENERATION,
    SYSTEM_PROMPT_AUDIT_EVALUATION,
)

__all__ = [
    # 模型
    "Indicator",
    "IndicatorBatch",
    "IndicatorQuery",
    "AuditRequest",
    "AuditResult",
    "CompletionStatus",
    "ConfidenceLevel",
    "EvidenceLocation",
    # 服务
    "IndicatorStore",
    "IndicatorService",
    # 路由
    "indicators_router",
    # 提示词
    "get_qa_prompt",
    "get_extraction_prompt",
    "get_table_prompt",
    "get_audit_prompt",
    "SYSTEM_PROMPT_SMART_QA",
    "SYSTEM_PROMPT_INDICATOR_EXTRACTION",
    "SYSTEM_PROMPT_TABLE_GENERATION",
    "SYSTEM_PROMPT_AUDIT_EVALUATION",
]

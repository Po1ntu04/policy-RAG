"""指标数据模型 - 用于政务指标表的结构化存储与管理"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CompletionStatus(str, Enum):
    """指标状态"""
    COMPLETED = "已完成"
    IN_PROGRESS = "进行中"
    NOT_COMPLETED = "未启动"
    PENDING = "待评估"
    UNKNOWN = "无法判断"


class ConfidenceLevel(str, Enum):
    """置信度等级"""
    HIGH = "high"      # 高置信度：多个来源一致确认
    MEDIUM = "medium"  # 中置信度：单一来源或有轻微歧义
    LOW = "low"        # 低置信度：推断或信息不完整
    MANUAL = "manual"  # 人工录入


class EvidenceLocation(BaseModel):
    """证据定位信息"""
    doc_id: str = Field(description="来源文档ID")
    doc_name: str = Field(description="来源文档名称")
    text_snippet: Optional[str] = Field(None, description="证据文本片段（前200字）")
    chunk_id: Optional[str] = Field(None, description="对应的chunk ID")


class Indicator(BaseModel):
    """政务指标数据结构 - V1 完整版"""
    
    # === 核心标识 ===
    id: Optional[str] = Field(None, description="指标唯一ID")
    policy_id: Optional[str] = Field(None, description="关联政策文件ID")
    
    # === 基本信息（与目标表对应） ===
    year: int = Field(description="年度")
    primary_category: str = Field(description="一级指标")
    secondary_indicator: str = Field(description="二级指标")
    scoring_rules: Optional[str] = Field(None, description="评分细则")
    score: Optional[float] = Field(None, description="分值")
    
    # === 来源与时限 ===
    target_source: Optional[str] = Field(None, description="目标来源（政策文件引用）")
    deadline: Optional[date] = Field(None, description="完成时限")
    
    # === 完成状态 ===
    completion_status: CompletionStatus = Field(
        default=CompletionStatus.NOT_COMPLETED,
        description="是否完成"
    )
    
    # === 责任归属 ===
    responsible_unit: Optional[str] = Field(None, description="责任单位")
    responsible_department: Optional[str] = Field(None, description="责任处室")
    
    # === 证据与追溯（V1 新增） ===
    evidence_locations: list[EvidenceLocation] = Field(
        default_factory=list,
        description="证据定位列表"
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="置信度"
    )
    
    # === 审计相关（V1.5 预留） ===
    audit_result: Optional[str] = Field(None, description="审计判定结果")
    audit_reason: Optional[str] = Field(None, description="审计判定理由")
    audit_evidence: Optional[str] = Field(None, description="审计佐证材料引用")
    
    # === 元数据 ===
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    created_by: Optional[str] = Field(None, description="创建者（系统/人工）")
    version: int = Field(default=1, description="版本号")


class IndicatorBatch(BaseModel):
    """指标批量操作结构"""
    indicators: list[Indicator] = Field(description="指标列表")
    source_doc_id: Optional[str] = Field(None, description="来源文档ID")
    extraction_model: Optional[str] = Field(None, description="抽取使用的模型")
    extraction_prompt_version: Optional[str] = Field(None, description="抽取prompt版本")


class IndicatorQuery(BaseModel):
    """指标查询条件"""
    year: Optional[int] = Field(None, description="年度")
    years: Optional[list[int]] = Field(None, description="年度列表")
    primary_category: Optional[str] = Field(None, description="一级指标（模糊匹配）")
    responsible_unit: Optional[str] = Field(None, description="责任单位（模糊匹配）")
    deadline_from: Optional[date] = Field(None, description="完成时限起")
    deadline_to: Optional[date] = Field(None, description="完成时限止")
    completion_status: Optional[CompletionStatus] = Field(None, description="完成状态")
    keyword: Optional[str] = Field(None, description="关键词搜索")
    limit: int = Field(100, description="返回数量限制")
    offset: int = Field(0, description="分页偏移")


class IndicatorExportRequest(BaseModel):
    """指标导出请求"""
    query: IndicatorQuery = Field(description="查询条件")
    format: str = Field("xlsx", description="导出格式：xlsx/csv/json")
    include_evidence: bool = Field(True, description="是否包含证据定位")
    include_audit: bool = Field(False, description="是否包含审计结果")


class IndicatorExtractionRequest(BaseModel):
    """指标抽取请求"""
    doc_ids: Optional[list[str]] = Field(None, description="指定文档ID列表")
    year: Optional[int] = Field(None, description="指定年度")
    auto_save: bool = Field(True, description="是否自动保存到指标库")
    

class AuditRequest(BaseModel):
    """审计请求"""
    indicator_ids: Optional[list[str]] = Field(None, description="指定指标ID列表")
    indicator_query: Optional[IndicatorQuery] = Field(None, description="指标查询条件")
    evidence_doc_ids: Optional[list[str]] = Field(None, description="佐证材料文档ID")
    audit_rules: Optional[list[str]] = Field(None, description="自定义审计规则")
    audit_focus: Optional[str] = Field(None, description="审计重点（可选）")
    

class AuditResult(BaseModel):
    """审计结果"""
    indicator_id: str = Field(description="指标ID")
    indicator_summary: str = Field(description="指标摘要")
    judgment: str = Field(description="判定：达成/部分达成/未达成/无法判断")
    reason: str = Field(description="判定理由")
    evidence_refs: list[EvidenceLocation] = Field(description="支撑证据")
    confidence: ConfidenceLevel = Field(description="置信度")
    suggestions: Optional[str] = Field(None, description="改进建议")

"""
指标服务层 - 连接 LLM 与存储

实现核心业务逻辑：
1. 从文档中抽取指标
2. 批量导入指标
3. 审计评估指标完成情况
4. 查询和导出指标
"""

import json
import logging
from datetime import datetime
from typing import Optional

from injector import inject, singleton
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.chat_engine.types import BaseChatEngine

from private_gpt.components.llm.llm_component import LLMComponent
from private_gpt.server.chat.chat_service import ChatService
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
from private_gpt.server.indicators.prompts import (
    get_extraction_prompt,
    get_audit_prompt,
    get_qa_prompt,
)

logger = logging.getLogger(__name__)


@singleton
class IndicatorService:
    """指标服务 - 核心业务逻辑层"""
    
    @inject
    def __init__(
        self,
        llm_component: LLMComponent,
        chat_service: ChatService,
        indicator_store: IndicatorStore,
    ):
        self._llm = llm_component.llm
        self._chat_service = chat_service
        self._store = indicator_store
        logger.info("IndicatorService initialized")
    
    # =========================================================================
    # 指标抽取
    # =========================================================================
    
    async def extract_indicators_from_documents(
        self,
        doc_ids: list[str],
        year: Optional[int] = None,
        use_rag: bool = True,
    ) -> IndicatorBatch:
        """
        从指定文档中抽取指标
        
        Args:
            doc_ids: 要抽取的文档ID列表
            year: 聚焦的年度（可选）
            use_rag: 是否使用RAG检索增强
            
        Returns:
            IndicatorBatch: 抽取结果批次
        """
        logger.info(f"Starting indicator extraction from {len(doc_ids)} documents, year={year}")
        
        # 构建抽取提示词
        system_prompt = get_extraction_prompt(year)
        
        # 构建查询
        query = "请从以下文档内容中抽取所有绩效考核指标，按指定JSON格式输出。"
        if year:
            query += f" 重点关注{year}年度的指标。"
        
        try:
            # 构建消息列表，system_prompt 作为第一条 SYSTEM 消息
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessage(role=MessageRole.USER, content=query),
            ]
            
            if use_rag:
                # 使用RAG检索相关内容（同步调用）
                from private_gpt.open_ai.extensions.context_filter import ContextFilter
                ctx_filter = ContextFilter(docs_ids=doc_ids) if doc_ids else None
                result = self._chat_service.chat(
                    messages=messages,
                    use_context=True,
                    context_filter=ctx_filter,
                )
                response_text = result.response
            else:
                # 直接调用LLM
                response = await self._llm.achat(messages)
                response_text = response.message.content
            
            # 解析LLM响应
            indicators = self._parse_extraction_response(response_text)
            
            # 创建批次
            batch = IndicatorBatch(
                source_type="document_extraction",
                source_description=f"从{len(doc_ids)}个文档中抽取",
                indicators=indicators,
            )
            
            logger.info(f"Extracted {len(indicators)} indicators")
            return batch
            
        except Exception as e:
            logger.error(f"Indicator extraction failed: {e}", exc_info=True)
            raise
    
    def _parse_extraction_response(self, response: str) -> list[Indicator]:
        """解析LLM的抽取响应"""
        indicators = []
        
        try:
            # 尝试从响应中提取JSON
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                # 处理indicators数组
                raw_indicators = data.get("indicators", [])
                for idx, raw in enumerate(raw_indicators):
                    try:
                        indicator = self._convert_raw_to_indicator(raw, idx)
                        indicators.append(indicator)
                    except Exception as e:
                        logger.warning(f"Failed to parse indicator {idx}: {e}")
                        continue
                        
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            # 可以尝试更宽松的解析策略
        
        return indicators
    
    def _convert_raw_to_indicator(self, raw: dict, index: int) -> Indicator:
        """将原始字典转换为Indicator对象"""
        # 处理完成状态
        status_str = raw.get("completion_status", "待评估")
        status_map = {
            "已完成": CompletionStatus.COMPLETED,
            "未完成": CompletionStatus.NOT_COMPLETED,
            "未启动": CompletionStatus.NOT_COMPLETED,
            "部分完成": CompletionStatus.IN_PROGRESS,
            "进行中": CompletionStatus.IN_PROGRESS,
            "待评估": CompletionStatus.PENDING,
            "completed": CompletionStatus.COMPLETED,
            "in_progress": CompletionStatus.IN_PROGRESS,
            "not_completed": CompletionStatus.NOT_COMPLETED,
            "pending": CompletionStatus.PENDING,
        }
        completion_status = status_map.get(status_str, CompletionStatus.NOT_COMPLETED)
        
        # 处理完成时限
        deadline = None
        deadline_str = raw.get("deadline")
        if deadline_str:
            try:
                deadline = datetime.fromisoformat(deadline_str.replace('/', '-'))
            except:
                pass
        
        # 构建证据位置
        evidence = None
        evidence_text = raw.get("evidence_text")
        if evidence_text:
            evidence = EvidenceLocation(
                doc_id="unknown",
                doc_name=raw.get("target_source", "未知来源"),
                text_snippet=evidence_text[:500] if len(evidence_text) > 500 else evidence_text,
                chunk_id=None,
            )
        
        responsible_unit = raw.get("responsible_unit")
        if not str(responsible_unit or "").strip():
            responsible_unit = "未指定"
        responsible_department = raw.get("responsible_department")
        if not str(responsible_department or "").strip():
            responsible_department = "未指定"

        return Indicator(
            year=raw.get("year"),
            primary_category=raw.get("primary_category", ""),
            secondary_indicator=raw.get("secondary_indicator", ""),
            scoring_rules=raw.get("scoring_rules"),
            score=raw.get("score"),
            target_source=raw.get("target_source"),
            deadline=deadline,
            completion_status=completion_status,
            responsible_unit=responsible_unit,
            responsible_department=responsible_department,
            evidence_locations=[evidence] if evidence else [],
            extraction_confidence=ConfidenceLevel.MEDIUM,
        )
    
    # =========================================================================
    # 批量导入
    # =========================================================================
    
    def import_indicators(self, batch: IndicatorBatch, save: bool = True) -> int:
        """
        导入指标批次
        
        Args:
            batch: 指标批次
            save: 是否保存到存储
            
        Returns:
            int: 成功导入的数量
        """
        count = 0
        for indicator in batch.indicators:
            try:
                self._store.add(indicator)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to import indicator: {e}")
        
        if save:
            self._store.save()
        
        logger.info(f"Imported {count}/{len(batch.indicators)} indicators")
        return count
    
    # =========================================================================
    # 审计评估
    # =========================================================================
    
    async def audit_indicators(
        self,
        request: AuditRequest,
    ) -> list[AuditResult]:
        """
        对指标进行审计评估
        
        Args:
            request: 审计请求（包含指标ID和佐证材料）
            
        Returns:
            list[AuditResult]: 审计结果列表
        """
        logger.info(f"Starting audit for {len(request.indicator_ids)} indicators")
        
        results = []
        
        for indicator_id in request.indicator_ids:
            indicator = self._store.get(indicator_id)
            if not indicator:
                logger.warning(f"Indicator not found: {indicator_id}")
                continue
            
            try:
                result = await self._audit_single_indicator(
                    indicator=indicator,
                    evidence_doc_ids=request.evidence_doc_ids,
                    audit_focus=request.audit_focus,
                )
                results.append(result)
                
                # 更新指标的完成状态
                if result.judgment != "无法判断":
                    indicator.completion_status = self._judgment_to_status(result.judgment)
                    self._store.update(indicator)
                    
            except Exception as e:
                logger.error(f"Audit failed for {indicator_id}: {e}")
                results.append(AuditResult(
                    indicator_id=indicator_id,
                    judgment="无法判断",
                    reason=f"审计过程出错: {str(e)}",
                    confidence=ConfidenceLevel.LOW,
                ))
        
        self._store.save()
        logger.info(f"Audit completed with {len(results)} results")
        return results
    
    async def _audit_single_indicator(
        self,
        indicator: Indicator,
        evidence_doc_ids: Optional[list[str]],
        audit_focus: Optional[str],
    ) -> AuditResult:
        """审计单个指标"""
        system_prompt = get_audit_prompt(audit_focus)
        
        # 构建审计查询
        query = f"""请对以下指标进行审计评估：

## 待审核指标
- ID: {indicator.id}
- 年度: {indicator.year}
- 一级指标: {indicator.primary_category}
- 二级指标: {indicator.secondary_indicator}
- 评分细则: {indicator.scoring_rules or '无'}
- 分值: {indicator.score or '未指定'}
- 目标来源: {indicator.target_source or '未指定'}
- 完成时限: {indicator.deadline.isoformat() if indicator.deadline else '未指定'}
- 责任单位: {indicator.responsible_unit or '未指定'}

请根据已入库的佐证材料进行评估，按JSON格式输出审计结果。
"""
        
        # 构建消息列表并调用RAG进行审计
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=query),
        ]
        from private_gpt.open_ai.extensions.context_filter import ContextFilter
        ctx_filter = ContextFilter(docs_ids=evidence_doc_ids) if evidence_doc_ids else None
        result = self._chat_service.chat(
            messages=messages,
            use_context=True,
            context_filter=ctx_filter,
        )
        
        # 解析审计结果
        return self._parse_audit_response(indicator.id, result.response)
    
    def _parse_audit_response(self, indicator_id: str, response: str) -> AuditResult:
        """解析审计响应"""
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                # 处理可能的嵌套结构
                if "audit_results" in data and data["audit_results"]:
                    result_data = data["audit_results"][0]
                else:
                    result_data = data
                
                # 构建证据引用
                evidence_refs = []
                for ref in result_data.get("evidence_refs", []):
                    evidence_refs.append(
                        EvidenceLocation(
                            doc_id="unknown",
                            doc_name=ref.get("doc_name", ""),
                            text_snippet=ref.get("quote"),
                            chunk_id=None,
                        )
                    )
                
                # 解析置信度
                conf_str = result_data.get("confidence", "medium")
                conf_map = {
                    "high": ConfidenceLevel.HIGH,
                    "medium": ConfidenceLevel.MEDIUM,
                    "low": ConfidenceLevel.LOW,
                }
                confidence = conf_map.get(conf_str.lower(), ConfidenceLevel.MEDIUM)
                
                return AuditResult(
                    indicator_id=indicator_id,
                    judgment=result_data.get("judgment", "无法判断"),
                    score_achieved=result_data.get("score_achieved"),
                    score_total=result_data.get("score_total"),
                    reason=result_data.get("reason", ""),
                    evidence_refs=evidence_refs,
                    confidence=confidence,
                    suggestions=result_data.get("suggestions"),
                )
                
        except Exception as e:
            logger.warning(f"Failed to parse audit response: {e}")
        
        return AuditResult(
            indicator_id=indicator_id,
            judgment="无法判断",
            reason="响应解析失败",
            confidence=ConfidenceLevel.LOW,
        )
    
    def _judgment_to_status(self, judgment: str) -> CompletionStatus:
        """将审计判定转换为完成状态"""
        status_map = {
            "达成": CompletionStatus.COMPLETED,
            "部分达成": CompletionStatus.IN_PROGRESS,
            "未达成": CompletionStatus.NOT_COMPLETED,
        }
        return status_map.get(judgment, CompletionStatus.PENDING)
    
    # =========================================================================
    # 查询接口
    # =========================================================================
    
    def query_indicators(self, query: IndicatorQuery) -> list[Indicator]:
        """查询指标"""
        return self._store.query(query)
    
    def get_indicator(self, indicator_id: str) -> Optional[Indicator]:
        """获取单个指标"""
        return self._store.get(indicator_id)
    
    def get_all_indicators(self) -> list[Indicator]:
        """获取所有指标"""
        return self._store.get_all()
    
    def delete_indicator(self, indicator_id: str) -> bool:
        """删除指标"""
        result = self._store.delete(indicator_id)
        if result:
            self._store.save()
        return result
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        return self._store.get_statistics()
    
    def export_to_excel(self, filepath: str, query: Optional[IndicatorQuery] = None) -> str:
        """导出为Excel"""
        import pandas as pd
        
        if query:
            indicators = self._store.query(query)
        else:
            indicators = self._store.get_all()
        
        df = self._store.export_to_dataframe(indicators)
        df.to_excel(filepath, index=False, engine='openpyxl')
        
        logger.info(f"Exported {len(indicators)} indicators to {filepath}")
        return filepath

"""指标存储服务 - 管理指标的持久化、查询、导出"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from private_gpt.server.indicators.models import (
    CompletionStatus,
    ConfidenceLevel,
    Indicator,
    IndicatorBatch,
    IndicatorQuery,
)
from private_gpt.settings.settings import settings

logger = logging.getLogger(__name__)


class IndicatorStore:
    """指标存储服务 - 基于 JSON 文件的简单实现，可扩展为数据库"""

    def __init__(self) -> None:
        self._data_dir = Path(settings().data.local_data_folder) / "indicators"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._data_dir / "indicators_index.json"
        self._indicators: dict[str, Indicator] = {}
        self._load()

    def _load(self) -> None:
        """加载指标索引"""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("indicators", []):
                    if item.get("completion_status") == "未完成":
                        item["completion_status"] = "未启动"
                    if item.get("completion_status") not in (
                        "已完成",
                        "进行中",
                        "未启动",
                        "待评估",
                        "无法判断",
                    ):
                        item["completion_status"] = "未启动"
                    if not str(item.get("responsible_unit") or "").strip():
                        item["responsible_unit"] = "未指定"
                    if not str(item.get("responsible_department") or "").strip():
                        item["responsible_department"] = "未指定"
                    ind = Indicator(**item)
                    if ind.id:
                        self._indicators[ind.id] = ind
                logger.info("已加载 %d 条指标", len(self._indicators))
            except Exception as e:
                logger.error("加载指标索引失败: %s", e)

    def _save(self) -> None:
        """保存指标索引"""
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "indicators": [ind.model_dump(mode="json") for ind in self._indicators.values()],
            }
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("保存指标索引失败: %s", e)

    def add(self, indicator: Indicator) -> Indicator:
        """添加单个指标"""
        if not indicator.id:
            indicator.id = str(uuid.uuid4())
        if not (indicator.responsible_unit or "").strip():
            indicator.responsible_unit = "未指定"
        if not (indicator.responsible_department or "").strip():
            indicator.responsible_department = "未指定"
        indicator.created_at = datetime.now()
        indicator.updated_at = datetime.now()
        self._indicators[indicator.id] = indicator
        self._save()
        return indicator

    def add_batch(self, batch: IndicatorBatch) -> list[Indicator]:
        """批量添加指标"""
        added = []
        for ind in batch.indicators:
            if not ind.id:
                ind.id = str(uuid.uuid4())
            if not (ind.responsible_unit or "").strip():
                ind.responsible_unit = "未指定"
            if not (ind.responsible_department or "").strip():
                ind.responsible_department = "未指定"
            ind.created_at = datetime.now()
            ind.updated_at = datetime.now()
            self._indicators[ind.id] = ind
            added.append(ind)
        self._save()
        logger.info("批量添加 %d 条指标", len(added))
        return added

    def update(self, indicator_id: str, updates: dict) -> Optional[Indicator]:
        """更新指标"""
        if indicator_id not in self._indicators:
            return None
        ind = self._indicators[indicator_id]
        for key, value in updates.items():
            if hasattr(ind, key):
                if key in ("responsible_unit", "responsible_department"):
                    if not str(value or "").strip():
                        value = "未指定"
                setattr(ind, key, value)
        ind.updated_at = datetime.now()
        ind.version += 1
        self._indicators[indicator_id] = ind
        self._save()
        return ind

    def delete(self, indicator_id: str) -> bool:
        """删除指标"""
        if indicator_id in self._indicators:
            del self._indicators[indicator_id]
            self._save()
            return True
        return False

    def get(self, indicator_id: str) -> Optional[Indicator]:
        """获取单个指标"""
        return self._indicators.get(indicator_id)

    def query(self, q: IndicatorQuery) -> list[Indicator]:
        """查询指标"""
        results = list(self._indicators.values())

        # 年度筛选
        if q.year:
            results = [ind for ind in results if ind.year == q.year]
        if q.years:
            results = [ind for ind in results if ind.year in q.years]

        # 一级指标筛选（模糊匹配）
        if q.primary_category:
            keyword = q.primary_category.lower()
            results = [
                ind for ind in results
                if keyword in ind.primary_category.lower()
            ]

        # 责任单位筛选（模糊匹配）
        if q.responsible_unit:
            keyword = q.responsible_unit.lower()
            results = [
                ind for ind in results
                if ind.responsible_unit and keyword in ind.responsible_unit.lower()
            ]

        # 完成时限筛选
        if q.deadline_from:
            results = [
                ind for ind in results
                if ind.deadline and ind.deadline >= q.deadline_from
            ]
        if q.deadline_to:
            results = [
                ind for ind in results
                if ind.deadline and ind.deadline <= q.deadline_to
            ]

        # 完成状态筛选
        if q.completion_status:
            results = [
                ind for ind in results
                if ind.completion_status == q.completion_status
            ]

        # 关键词搜索（在多个字段中搜索）
        if q.keyword:
            keyword = q.keyword.lower()
            filtered = []
            for ind in results:
                searchable = " ".join([
                    ind.primary_category or "",
                    ind.secondary_indicator or "",
                    ind.scoring_rules or "",
                    ind.target_source or "",
                    ind.responsible_unit or "",
                    ind.responsible_department or "",
                ]).lower()
                if keyword in searchable:
                    filtered.append(ind)
            results = filtered

        # 排序（按年度降序，再按一级指标）
        results.sort(key=lambda x: (-x.year, x.primary_category))

        # 分页
        start = q.offset
        end = start + q.limit
        page = results[start:end]
        for ind in page:
            if not ind.responsible_unit:
                ind.responsible_unit = "未指定"
            if not ind.responsible_department:
                ind.responsible_department = "未指定"
        return page

    def count(self, q: Optional[IndicatorQuery] = None) -> int:
        """统计数量"""
        if q is None:
            return len(self._indicators)
        data = q.model_dump()
        data["limit"] = 999999
        data["offset"] = 0
        return len(self.query(IndicatorQuery(**data)))

    def get_statistics(self) -> dict:
        """获取统计信息"""
        total = len(self._indicators)
        by_year: dict[int, int] = {}
        by_status: dict[str, int] = {}
        by_unit: dict[str, int] = {}

        for ind in self._indicators.values():
            by_year[ind.year] = by_year.get(ind.year, 0) + 1
            by_status[ind.completion_status.value] = by_status.get(ind.completion_status.value, 0) + 1
            if ind.responsible_unit:
                by_unit[ind.responsible_unit] = by_unit.get(ind.responsible_unit, 0) + 1

        return {
            "total": total,
            "by_year": by_year,
            "by_status": by_status,
            "by_unit": dict(sorted(by_unit.items(), key=lambda x: -x[1])[:20]),
        }

    def export_to_dataframe(self, q: IndicatorQuery):
        """???DataFrame???Excel???"""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("????pandas: pip install pandas")

        indicators = self.query(q)
        columns = [
            "年度",
            "一级指标",
            "二级指标",
            "评分细则",
            "分值",
            "目标来源",
            "完成时限",
            "是否完成",
            "责任单位",
            "责任处室",
            "证据引用",
            "置信度",
        ]
        rows = []
        def _wrap_source(value: Optional[str]) -> Optional[str]:
            if not value:
                return value
            text = str(value)
            if "《" in text and "》" in text:
                return text
            return f"《{text}》"

        for ind in indicators:
            evidence_refs = ""
            if ind.evidence_locations:
                evidence_refs = "; ".join(
                    [e.doc_name for e in ind.evidence_locations if e.doc_name]
                )
            row = {
                "年度": ind.year,
                "一级指标": ind.primary_category,
                "二级指标": ind.secondary_indicator,
                "评分细则": ind.scoring_rules,
                "分值": ind.score,
                "目标来源": _wrap_source(ind.target_source),
                "完成时限": ind.deadline.isoformat() if ind.deadline else None,
                "是否完成": ind.completion_status.value,
                "责任单位": ind.responsible_unit,
                "责任处室": ind.responsible_department,
                "证据引用": evidence_refs,
                "置信度": ind.confidence.value,
            }
            rows.append(row)

        return pd.DataFrame(rows, columns=columns)



# 全局单例
_indicator_store: Optional[IndicatorStore] = None


def get_indicator_store() -> IndicatorStore:
    """获取指标存储服务单例"""
    global _indicator_store
    if _indicator_store is None:
        store_mode = os.getenv("PGPT_INDICATOR_STORE", "json").lower()
        if store_mode == "postgres":
            from private_gpt.server.indicators.indicator_store_postgres import (
                PostgresIndicatorStore,
            )

            logger.info("Using PostgresIndicatorStore for indicators.")
            _indicator_store = PostgresIndicatorStore()  # type: ignore[assignment]
        else:
            logger.info("Using Json IndicatorStore for indicators.")
            _indicator_store = IndicatorStore()
    return _indicator_store

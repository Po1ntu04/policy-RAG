<template>
  <div class="audit-evaluation-container">
    <div class="audit-layout">
      <!-- 左侧配置面板 -->
      <div class="config-panel">
        <a-card title="活动审计配置">
          <a-form layout="vertical">
            <a-form-item label="活动名称" required>
              <a-input
                v-model:value="auditConfig.activityName"
                placeholder="请输入活动名称"
              />
            </a-form-item>

            <a-form-item label="活动描述/完成情况" required>
              <a-textarea
                v-model:value="auditConfig.activityDescription"
                placeholder="简要描述审计目标与情况"
                :rows="3"
              />
            </a-form-item>
            
            
            
            <a-form-item label="说明">
              <a-alert type="info" show-icon :message="'系统将根据活动描述自动抽取评估指标并进行对照核验，无需手动填写指标。'" />
            </a-form-item>

            <a-form-item label="审计选项">
              <div class="audit-options">
                <div class="option-item">
                  <a-checkbox v-model:checked="auditConfig.includeRecommendations">
                    包含改进建议
                  </a-checkbox>
                </div>
                <div class="option-item">
                  <a-checkbox v-model:checked="auditConfig.detailedAnalysis">
                    详细分析
                  </a-checkbox>
                </div>
              </div>
            </a-form-item>
          </a-form>
          
          <div class="action-buttons">
            <a-button 
              type="primary" 
              block
              :loading="isAuditing"
              :disabled="!canStartAudit"
              @click="startAudit"
            >
              <template #icon>
                <audit-outlined />
              </template>
              开始评估
            </a-button>
            
            <a-button 
              block
              @click="resetConfig"
              :disabled="isAuditing"
            >
              重置配置
            </a-button>
          </div>
        </a-card>
      </div>
      
      <!-- 右侧结果展示 -->
      <div class="result-panel">
        <!-- 审计中状态 -->
        <div v-if="isAuditing" class="auditing-state">
          <a-spin size="large" />
          <div class="auditing-text">
            <h3>正在执行活动评估</h3>
            <p>正在分析相关文档并核验指标完成情况，请稍候...</p>
            <div class="audit-progress">
              <a-progress 
                :percent="auditProgress" 
                :show-info="true"
                status="active"
              />
            </div>
          </div>
        </div>
        
        <!-- 评估结果 -->
        <div v-else-if="currentReport" class="audit-result">
          <a-card>
            <template #title>
              <div class="report-header">
                <div class="report-title">
                  <audit-outlined />
                  活动审计评估报告
                </div>
                <div class="report-actions">
                  <a-button @click="exportReport">
                    <template #icon>
                      <download-outlined />
                    </template>
                    导出报告
                  </a-button>
                  
                  <a-button @click="saveReport">
                    <template #icon>
                      <save-outlined />
                    </template>
                    保存
                  </a-button>
                </div>
              </div>
            </template>
            
            <!-- 总体结果与摘要 -->
            <div class="audit-summary">
              <a-row :gutter="16">
                <a-col :span="8">
                  <div>
                    <div style="margin-bottom: 8px; color:#8c8c8c">总体完成</div>
                    <a-tag :color="currentReport.overallCompleted ? 'green' : 'red'">
                      {{ currentReport.overallCompleted ? '已完成' : '未完成' }}
                    </a-tag>
                  </div>
                </a-col>
                <a-col :span="8">
                  <a-statistic 
                    title="综合评分" 
                    :value="Number(currentReport.overallScore || 0)" 
                    suffix="分"
                    :value-style="{ color: getScoreColor(Number(currentReport.overallScore || 0)) }"
                  />
                </a-col>
                <a-col :span="8">
                  <a-statistic 
                    title="审查文档" 
                    :value="currentReport.totalDocumentsReviewed || 0" 
                    suffix="个"
                  />
                </a-col>
              </a-row>
            </div>
            
            <!-- 摘要文本 -->
            <div class="report-summary" v-if="currentReport.summary">
              <h4>审计摘要</h4>
              <p>{{ currentReport.summary }}</p>
            </div>
            
            <!-- 指标结果表 -->
            <div class="indicators-section">
              <h4>指标评估</h4>
              <a-table
                :data-source="currentReport.indicatorResults || []"
                :pagination="false"
                :row-key="(_, i) => i"
              >
                <a-table-column key="name" title="指标名称" data-index="name" />
                <a-table-column key="target" title="目标值" data-index="target" />
                <a-table-column key="actual" title="实际完成" data-index="actual" />
                <a-table-column key="unit" title="单位" data-index="unit" />
                <a-table-column key="status" title="状态">
                  <template #default="{ record }">
                    <a-tag :color="getStatusColor(record.status)">{{ record.status }}</a-tag>
                  </template>
                </a-table-column>
                <a-table-column key="score" title="得分">
                  <template #default="{ record }">
                    <span :style="{ color: getScoreColor(Number(record.score || 0)) }">{{ Number(record.score || 0) }}</span>
                  </template>
                </a-table-column>
                <a-table-column key="evidence" title="证据/备注">
                  <template #default="{ record }">
                    <span>{{ record.evidence || record.notes || '-' }}</span>
                  </template>
                </a-table-column>
              </a-table>
            </div>
            
            <!-- 主要建议 -->
            <div class="recommendations-section" v-if="currentReport.recommendationsSummary && currentReport.recommendationsSummary.length > 0">
              <h4>主要改进建议</h4>
              <ul class="recommendations-list">
                <li v-for="(recommendation, index) in currentReport.recommendationsSummary" :key="index">
                  {{ recommendation }}
                </li>
              </ul>
            </div>
            
            <!-- 报告元信息 -->
            <div class="report-meta">
              <a-descriptions size="small" :column="3">
                <a-descriptions-item label="活动名称" v-if="currentReport.activityName">
                  {{ currentReport.activityName }}
                </a-descriptions-item>
                <a-descriptions-item label="生成时间">
                  {{ formatTime(currentReport.generatedAt) }}
                </a-descriptions-item>
                <a-descriptions-item label="报告ID">
                  {{ currentReport.reportId }}
                </a-descriptions-item>
              </a-descriptions>
            </div>
          </a-card>
        </div>
        
        <!-- 初始状态 -->
        <div v-else class="empty-state">
          <div class="empty-content">
            <audit-outlined class="empty-icon" />
            <h3>开始您的活动审计评估</h3>
            <p>请在左侧配置活动与指标，然后点击开始评估</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, reactive } from 'vue'
import { useStore } from 'vuex'
import { message } from 'ant-design-vue'
import {
  AuditOutlined,
  DownloadOutlined,
  SaveOutlined
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'

export default {
  name: 'AuditEvaluation',
  components: {
    AuditOutlined,
    DownloadOutlined,
    SaveOutlined
  },
  setup() {
    const store = useStore()
    
    // 审计配置
    const auditConfig = reactive({
      activityName: '',
      activityDescription: '',
      // 范围（部门、时间）改为在描述中提供，无需单独选择
      // 指标由系统根据描述自动抽取
      includeRecommendations: true,
      detailedAnalysis: true
    })
    
    // 界面状态
    const auditProgress = ref(0)
    
    // 计算属性
    const isAuditing = computed(() => store.getters['audit/isAuditing'])
    const currentReport = computed(() => store.state.audit.currentReport)
    
    const canStartAudit = computed(() => {
      return Boolean(auditConfig.activityName && auditConfig.activityDescription)
    })
    
    // 方法
    const getScoreColor = (score) => {
      if (score >= 90) return '#52c41a'
      if (score >= 70) return '#faad14'
      if (score >= 50) return '#fa8c16'
      return '#ff4d4f'
    }
    
    const getSourceName = (source) => {
      if (source.document && source.document.doc_metadata) {
        return source.document.doc_metadata.file_name || '未知文档'
      }
      return '文档片段'
    }

    const getStatusColor = (status) => {
      const s = String(status || '').toLowerCase()
      if (s.includes('完成') || s.includes('通过') || s === 'completed' || s === 'pass') return 'green'
      if (s.includes('部分') || s === 'partial') return 'orange'
      return 'red'
    }

    const startAudit = async () => {
      if (!canStartAudit.value) {
        message.warning('请完善审计配置')
        return
      }
      
      // 模拟进度更新
      const progressInterval = setInterval(() => {
        auditProgress.value = Math.min(auditProgress.value + 10, 90)
      }, 500)
      
      try {
        const contextFilter = null
        
        await store.dispatch('audit/conductAudit', {
          auditType: 'activity',
          activityName: auditConfig.activityName,
          activityDescription: auditConfig.activityDescription,
          contextFilter,
          includeRecommendations: auditConfig.includeRecommendations,
          detailedAnalysis: auditConfig.detailedAnalysis
        })
        
        auditProgress.value = 100
        message.success('审计完成')
        
      } catch (error) {
        message.error('审计失败：' + error.message)
      } finally {
        clearInterval(progressInterval)
        setTimeout(() => {
          auditProgress.value = 0
        }, 1000)
      }
    }
    
    const resetConfig = () => {
      auditConfig.activityName = ''
      auditConfig.activityDescription = ''
      // 部门/时间范围改由描述提供
      // 无需重置指标
      auditConfig.includeRecommendations = true
      auditConfig.detailedAnalysis = true
      
      store.dispatch('audit/resetConfig')
    }
    
    const saveReport = async () => {
      if (!currentReport.value) return
      
      try {
        await store.dispatch('audit/saveReport', currentReport.value)
        message.success('报告保存成功')
      } catch (error) {
        message.error('保存失败：' + error.message)
      }
    }
    
    const exportReport = async () => {
      if (!currentReport.value) return
      
      try {
        await store.dispatch('audit/exportReport', {
          reportId: currentReport.value.reportId,
          format: 'pdf'
        })
        message.success('正在导出报告')
      } catch (error) {
        message.error('导出失败：' + error.message)
      }
    }
    
    const formatTime = (timestamp) => {
      return dayjs(timestamp).format('YYYY-MM-DD HH:mm')
    }
    
    return {
      auditConfig,
      auditProgress,
      isAuditing,
      currentReport,
      canStartAudit,
      getScoreColor,
      getSourceName,
      getStatusColor,
      startAudit,
      resetConfig,
      saveReport,
      exportReport,
      formatTime
    }
  }
}
</script>

<style lang="less" scoped>
.audit-evaluation-container {
  height: calc(100vh - 64px);
  background: #f0f2f5;
}

.audit-layout {
  height: 100%;
  display: flex;
  padding: 24px;
  gap: 24px;
}

.config-panel {
  width: 350px;
  
  .audit-scope {
    .scope-item {
      margin-bottom: 16px;
      
      &:last-child {
        margin-bottom: 0;
      }
    }
  }
  
  .audit-options {
    .option-item {
      margin-bottom: 8px;
      
      &:last-child {
        margin-bottom: 0;
      }
    }
  }

  .indicators {
    display: flex;
    flex-direction: column;
    gap: 12px;
    
    .indicator-item {
      padding: 12px;
      border: 1px dashed #d9d9d9;
      border-radius: 6px;
      background: #fafafa;
      display: flex;
      flex-direction: column;
      gap: 8px;
      
      .row {
        display: flex;
        gap: 8px;
      }
    }
  }
  
  .action-buttons {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 24px;
  }
}

.result-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.auditing-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 8px;
  
  .auditing-text {
    margin-top: 24px;
    text-align: center;
    width: 300px;
    
    h3 {
      margin: 0 0 8px 0;
      font-size: 18px;
      color: #262626;
    }
    
    p {
      margin: 0 0 20px 0;
      color: #8c8c8c;
    }
    
    .audit-progress {
      width: 100%;
    }
  }
}

.audit-result {
  flex: 1;
  
  :deep(.ant-card) {
    height: 100%;
    display: flex;
    flex-direction: column;
    
    .ant-card-body {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: auto;
    }
  }
  
  .report-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    
    .report-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 500;
    }
    
    .report-actions {
      display: flex;
      gap: 8px;
    }
  }
  
  .audit-summary {
    margin-bottom: 24px;
    padding: 16px;
    background: #fafafa;
    border-radius: 6px;
  }
  
  .report-summary {
    margin-bottom: 24px;
    
    h4 {
      margin-bottom: 8px;
    }
    
    p {
      color: #595959;
      line-height: 1.6;
    }
  }
  
  .indicators-section {
    margin-bottom: 24px;
    
    h4 {
      margin-bottom: 12px;
    }
  }
  
  .recommendations-section {
    margin-bottom: 24px;
    
    h4 {
      margin-bottom: 12px;
    }
    
    .recommendations-list {
      margin-left: 20px;
      
      li {
        margin-bottom: 8px;
        color: #595959;
        line-height: 1.6;
      }
    }
  }
  
  .report-meta {
    margin-top: auto;
    padding-top: 16px;
    border-top: 1px solid #f0f0f0;
  }
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 8px;
  
  .empty-content {
    text-align: center;
    
    .empty-icon {
      font-size: 48px;
      color: #d9d9d9;
      margin-bottom: 16px;
    }
    
    h3 {
      margin: 0 0 8px 0;
      font-size: 16px;
      color: #595959;
    }
    
    p {
      margin: 0;
      color: #8c8c8c;
    }
  }
}
</style>
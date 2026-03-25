<template>
  <div class="indicators-container">
    <div class="indicators-layout">
      <!-- 左侧筛选面板 -->
      <div class="filter-panel">
        <a-card title="筛选条件" size="small">
          <a-form layout="vertical" size="small">
            <a-form-item label="年度">
              <a-select
                v-model:value="filters.year"
                allowClear
                placeholder="选择年度"
              >
                <a-select-option
                  v-for="year in availableYears"
                  :key="year"
                  :value="year"
                >
                  {{ year }}年
                </a-select-option>
              </a-select>
            </a-form-item>

            <a-form-item label="一级指标">
              <a-select
                v-model:value="filters.primaryCategory"
                allowClear
                placeholder="选择分类"
              >
                <a-select-option
                  v-for="cat in availableCategories"
                  :key="cat"
                  :value="cat"
                >
                  {{ cat }}
                </a-select-option>
              </a-select>
            </a-form-item>

              <a-form-item label="完成状态">
                <a-select
                  v-model:value="filters.completionStatus"
                  allowClear
                  placeholder="选择状态"
                >
                  <a-select-option value="已完成">已完成</a-select-option>
                  <a-select-option value="进行中">进行中</a-select-option>
                  <a-select-option value="未启动">未启动</a-select-option>
                </a-select>
              </a-form-item>

            <a-form-item label="完成时限">
              <a-range-picker
                v-model:value="filters.deadlineRange"
                style="width: 100%"
                placeholder="开始日期,结束日期"
              />
            </a-form-item>

            <a-form-item label="责任单位">
              <a-input
                v-model:value="filters.responsibleUnit"
                placeholder="输入单位名称"
                allowClear
              />
            </a-form-item>

            <a-form-item label="关键词">
              <a-input
                v-model:value="filters.keyword"
                placeholder="搜索指标内容"
                allowClear
              />
            </a-form-item>
          </a-form>

          <div class="filter-actions">
            <a-button type="primary" block @click="searchIndicators">
              <template #icon><search-outlined /></template>
              搜索
            </a-button>
            <a-button block @click="resetFilters">重置</a-button>
          </div>
        </a-card>

        <a-card title="统计概览" size="small" style="margin-top: 16px">
          <a-statistic
            title="指标总数"
            :value="statistics.total"
            style="margin-bottom: 16px"
          />

          <div class="status-stats">
            <div class="stat-item">
              <span class="stat-label">已完成</span>
              <a-tag color="green">{{ statistics.by_status?.['已完成'] || 0 }}</a-tag>
            </div>
            <div class="stat-item">
              <span class="stat-label">进行中</span>
              <a-tag color="orange">{{ statistics.by_status?.['进行中'] || statistics.by_status?.['部分完成'] || 0 }}</a-tag>
            </div>
            <div class="stat-item">
              <span class="stat-label">未启动</span>
              <a-tag color="red">{{ statistics.by_status?.['未启动'] || statistics.by_status?.['未完成'] || 0 }}</a-tag>
            </div>
          </div>
        </a-card>
      </div>

      <!-- 右侧主内容 -->
      <div class="main-panel">
        <!-- 工具栏 -->
        <div class="toolbar">
          <div class="toolbar-left">
            <a-button v-if="!isPublic" type="primary" @click="showExtractModal">
              <template #icon><robot-outlined /></template>
              智能抽取
            </a-button>
            <a-button v-if="!isPublic" @click="showImportModal">
              <template #icon><upload-outlined /></template>
              导入Excel
            </a-button>
            <a-button @click="exportToExcel">
              <template #icon><download-outlined /></template>
              导出Excel
            </a-button>
          </div>

          <div class="toolbar-right">
            <a-space v-if="isAdmin">
              <a-select
                v-model:value="batchStatus"
                size="small"
                style="width: 120px"
              >
                <a-select-option value="未启动">未启动</a-select-option>
                <a-select-option value="进行中">进行中</a-select-option>
                <a-select-option value="已完成">已完成</a-select-option>
              </a-select>
              <a-button
                type="primary"
                :disabled="selectedRowKeys.length === 0"
                @click="applyBatchStatus()"
              >
                批量设置状态
              </a-button>
            </a-space>
            <a-button
              v-if="isLeader"
              type="primary"
              :disabled="selectedRowKeys.length === 0"
              @click="applyBatchStatus('进行中')"
            >
              批量启用
            </a-button>
            <a-button
              v-if="!isPublic"
              type="primary"
              danger
              :disabled="selectedRowKeys.length === 0"
              @click="showAuditModal"
            >
              <template #icon><audit-outlined /></template>
              批量审计 ({{ selectedRowKeys.length }})
            </a-button>
          </div>
        </div>

        <!-- 指标表格 -->
        <a-table
          :columns="columns"
          :data-source="indicators"
          :loading="loading"
          :pagination="pagination"
          :row-selection="rowSelection"
          row-key="id"
          size="small"
          bordered
          :scroll="{ x: 1800 }"
          @change="handleTableChange"
        >
          <template #bodyCell="{ column, text, record }">
            <template v-if="column.key === 'completion_status'">
              <a-tag :color="getStatusColor(record.completion_status)">
                {{ getStatusText(record.completion_status) }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'score'">
              <span class="score-cell">{{ text || '-' }}</span>
            </template>
            <template v-else-if="column.key === 'action'">
              <a-space>
                <a-button type="link" size="small" @click="viewDetail(record)">
                  详情
                </a-button>
                <a-button
                  v-if="!isPublic"
                  type="link"
                  size="small"
                  @click="editIndicator(record)"
                >
                  编辑
                </a-button>
                <a-popconfirm
                  v-if="!isPublic"
                  title="确定删除此指标吗？"
                  @confirm="deleteIndicator(record.id)"
                >
                  <a-button type="link" danger size="small">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </div>
    </div>

    <!-- 智能抽取弹窗 -->
    <a-modal
      v-model:open="extractModalVisible"
      title="智能抽取指标"
      width="600px"
      @ok="handleExtract"
      :confirmLoading="extracting"
    >
      <a-form layout="vertical">
        <a-card title="筛选文档" size="small" style="margin-bottom: 12px">
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="年份">
                <a-select
                  v-model:value="docFilters.year"
                  allow-clear
                  placeholder="选择年份"
                >
                  <a-select-option
                    v-for="year in docFilterOptions.years"
                    :key="year"
                    :value="year"
                  >
                    {{ year }}年
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="责任单位">
                <a-select
                  v-model:value="docFilters.responsibleUnit"
                  allow-clear
                  show-search
                  placeholder="选择责任单位"
                >
                  <a-select-option
                    v-for="unit in docFilterOptions.units"
                    :key="unit"
                    :value="unit"
                  >
                    {{ unit }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="责任处室">
                <a-select
                  v-model:value="docFilters.responsibleDepartment"
                  allow-clear
                  show-search
                  placeholder="选择责任处室"
                >
                  <a-select-option
                    v-for="dept in docFilterOptions.departments"
                    :key="dept"
                    :value="dept"
                  >
                    {{ dept }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="关键词">
                <a-input
                  v-model:value="docFilters.keyword"
                  placeholder="文档标题关键词"
                  allowClear
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-space>
            <a-button type="primary" :loading="docLoading" @click="applyDocFilters">
              筛选
            </a-button>
            <a-button @click="resetDocFilters">重置</a-button>
            <a-button :disabled="documentOptions.length === 0" @click="selectAllDocs">
              全选（筛选结果）
            </a-button>
            <a-button :disabled="extractConfig.policyIds.length === 0" @click="clearDocSelection">
              清空选择
            </a-button>
          </a-space>
        </a-card>

        <a-form-item label="选择文档">
          <a-select
            v-model:value="extractConfig.policyIds"
            mode="multiple"
            placeholder="选择要抽取的文档（留空则使用全部）"
            :options="documentOptions"
            :loading="docLoading"
            allowClear
          />
        </a-form-item>

        <a-form-item label="保存到存储">
          <a-switch v-model:checked="extractConfig.saveToStore" />
          <span style="margin-left: 8px; color: #8c8c8c">
            开启后抽取结果将自动保存
          </span>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 审计评估弹窗 -->
    <a-modal
      v-model:open="auditModalVisible"
      title="批量审计评估"
      width="700px"
      @ok="handleAudit"
      :confirmLoading="auditing"
    >
      <a-alert
        :message="`已选择 ${selectedRowKeys.length} 条指标进行审计`"
        type="info"
        show-icon
        style="margin-bottom: 16px"
      />

      <a-form layout="vertical">
        <a-form-item label="佐证材料">
          <a-select
            v-model:value="auditConfig.policyIds"
            mode="multiple"
            placeholder="选择佐证文档（留空则使用全部已入库文档）"
            :options="documentOptions"
            :loading="docLoading"
            allowClear
          />
        </a-form-item>

        <a-form-item label="审计重点">
          <a-textarea
            v-model:value="auditConfig.auditFocus"
            placeholder="可选，指定审计时需要特别关注的方面"
            :rows="3"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 指标详情弹窗 -->
    <a-modal
      v-model:open="detailModalVisible"
      title="指标详情"
      width="800px"
      :footer="null"
    >
      <a-descriptions v-if="currentIndicator" :column="2" bordered size="small">
        <a-descriptions-item label="ID">
          {{ currentIndicator.id }}
        </a-descriptions-item>
        <a-descriptions-item label="年度">
          {{ currentIndicator.year || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="一级指标" :span="2">
          {{ currentIndicator.primary_category }}
        </a-descriptions-item>
        <a-descriptions-item label="二级指标" :span="2">
          {{ currentIndicator.secondary_indicator }}
        </a-descriptions-item>
        <a-descriptions-item label="评分细则" :span="2">
          <div class="scoring-rules">
            {{ currentIndicator.scoring_rules || '-' }}
          </div>
        </a-descriptions-item>
        <a-descriptions-item label="分值">
          {{ currentIndicator.score || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="完成状态">
          <a-tag :color="getStatusColor(currentIndicator.completion_status)">
            {{ getStatusText(currentIndicator.completion_status) }}
          </a-tag>
        </a-descriptions-item>
          <a-descriptions-item label="目标来源" :span="2">
            {{ formatTargetSource(currentIndicator.target_source) }}
          </a-descriptions-item>
        <a-descriptions-item label="完成时限">
          {{ formatDate(currentIndicator.deadline) }}
        </a-descriptions-item>
        <a-descriptions-item label="责任单位">
          {{ currentIndicator.responsible_unit || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="责任处室" :span="2">
          {{ currentIndicator.responsible_department || '-' }}
        </a-descriptions-item>
      </a-descriptions>

      <div v-if="currentIndicator?.evidence_locations?.length" style="margin-top: 16px">
        <h4>证据来源</h4>
        <a-list
          :data-source="currentIndicator.evidence_locations"
          size="small"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>{{ item.doc_name }}</template>
                <template #description>
                    <span v-if="item.text_snippet || item.quote" class="quote-text">
                      "{{ item.text_snippet || item.quote }}"
                    </span>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
      </div>
    </a-modal>
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted, h } from 'vue'
import { useStore } from 'vuex'
import { message, Tooltip } from 'ant-design-vue'
import {
  SearchOutlined,
  RobotOutlined,
  UploadOutlined,
  DownloadOutlined,
  AuditOutlined,
} from '@ant-design/icons-vue'
import api from '@/services/api'
import dayjs from 'dayjs'

export default {
  name: 'IndicatorsManagement',
  components: {
    SearchOutlined,
    RobotOutlined,
    UploadOutlined,
    DownloadOutlined,
    AuditOutlined,
  },
  setup() {
    const store = useStore()
    // 状态
    const loading = ref(false)
    const indicators = ref([])
    const selectedRowKeys = ref([])
    const statistics = ref({ total: 0, byStatus: {}, byYear: {}, byPrimaryCategory: {} })
    const isPublic = computed(() => store.getters['auth/isPublic'])
    const roles = computed(() => store.getters['auth/roles'] || [])
    const isAdmin = computed(() => roles.value.includes('admin'))
    const isLeader = computed(() => roles.value.includes('leader'))
    
    // 筛选条件
    const filters = reactive({
      year: null,
      primaryCategory: null,
      completionStatus: null,
      deadlineRange: null,
      responsibleUnit: '',
      keyword: '',
    })

    // 分页
    const pagination = reactive({
      current: 1,
      pageSize: 20,
      total: 0,
      showSizeChanger: true,
      showQuickJumper: true,
      showTotal: (total) => `共 ${total} 条`,
    })

    const batchStatus = ref('未启动')

    // 弹窗控制
    const extractModalVisible = ref(false)
    const auditModalVisible = ref(false)
    const detailModalVisible = ref(false)
    const extracting = ref(false)
    const auditing = ref(false)
    const currentIndicator = ref(null)

    // 抽取配置
    const extractConfig = reactive({
      policyIds: [],
      saveToStore: true,
    })

    // 审计配置
    const auditConfig = reactive({
      policyIds: [],
      auditFocus: '',
    })

    // 文档筛选与选项
    const docFilters = reactive({
      year: null,
      responsibleUnit: null,
      responsibleDepartment: null,
      keyword: '',
    })

    const docFilterOptions = reactive({
      years: [],
      units: [],
      departments: [],
    })

    const docLoading = ref(false)
    const documentOptions = ref([])
    const documentMap = ref({})

    // 可用年度和分类
    const availableYears = computed(() => {
      const years = new Set()
      Object.keys(statistics.value.by_year || {}).forEach(y => years.add(parseInt(y)))
      return Array.from(years).sort((a, b) => b - a)
    })

    const availableCategories = computed(() => {
      // 当前后端统计不提供 by_primary_category，先从现有数据推断
      const seed = [
        '一、核心工作',
        '二、重点工作',
        '三、亮点工作',
        '四、考评工作',
        '五、创新工作',
        '六、鼓励工作',
      ]
      const cats = new Set(seed)
      indicators.value.forEach((i) => {
        if (i?.primary_category) cats.add(i.primary_category)
      })
      return Array.from(cats)
    })

    const formatTargetSource = (value) => {
      if (!value) return '-'
      const text = String(value)
      if (text.includes('《') && text.includes('》')) {
        return text
      }
      return `《${text}》`
    }

    const renderWithTooltip = (value) => {
      if (!value || value === '-') return '-'
      return h(
        Tooltip,
        { title: value },
        { default: () => h('span', value) }
      )
    }

    // 表格列定义
    const columns = [
      {
        title: '年度',
        dataIndex: 'year',
        key: 'year',
        width: 70,
        sorter: true,
      },
      {
        title: '一级指标',
        dataIndex: 'primary_category',
        key: 'primary_category',
        width: 150,
        ellipsis: true,
      },
        {
          title: '二级指标',
          dataIndex: 'secondary_indicator',
          key: 'secondary_indicator',
          width: 250,
          ellipsis: true,
        },
        {
          title: '评分细则',
          dataIndex: 'scoring_rules',
          key: 'scoring_rules',
          width: 260,
          ellipsis: true,
          customRender: ({ text }) => {
            const value = text ? String(text) : ''
            if (!value) {
              return '-'
            }
            return h(
              Tooltip,
              { title: value },
              { default: () => h('span', value) }
            )
          },
        },
        {
          title: '目标来源',
          dataIndex: 'target_source',
          key: 'target_source',
          width: 220,
          ellipsis: true,
          customRender: ({ text }) => renderWithTooltip(formatTargetSource(text)),
        },
        {
          title: '分值',
          dataIndex: 'score',
          key: 'score',
        width: 70,
        sorter: true,
      },
      {
        title: '完成状态',
        dataIndex: 'completion_status',
        key: 'completion_status',
        width: 100,
      },
      {
        title: '完成时限',
        dataIndex: 'deadline',
        key: 'deadline',
        width: 110,
        customRender: ({ text }) => text ? dayjs(text).format('YYYY-MM-DD') : '-',
      },
      {
        title: '责任单位',
        dataIndex: 'responsible_unit',
        key: 'responsible_unit',
        width: 120,
        ellipsis: true,
      },
      {
        title: '责任处室',
        dataIndex: 'responsible_department',
        key: 'responsible_department',
        width: 150,
        ellipsis: true,
      },
      {
        title: '操作',
        key: 'action',
        width: 150,
        fixed: 'right',
      },
    ]

    // 方法
    const fetchIndicators = async () => {
      loading.value = true
      try {
        const params = {
          skip: (pagination.current - 1) * pagination.pageSize,
          limit: pagination.pageSize,
        }
        if (filters.year) params.year = filters.year
        if (filters.primaryCategory) params.primary_category = filters.primaryCategory
        if (filters.completionStatus) params.completion_status = filters.completionStatus
        if (filters.deadlineRange && filters.deadlineRange.length === 2) {
          params.deadline_from = dayjs(filters.deadlineRange[0]).format('YYYY-MM-DD')
          params.deadline_to = dayjs(filters.deadlineRange[1]).format('YYYY-MM-DD')
        }
        if (filters.responsibleUnit) params.responsible_unit = filters.responsibleUnit
        if (filters.keyword) params.keyword = filters.keyword

        const response = await api.get('/indicators', { params })
        indicators.value = response.items
        pagination.total = response.total
      } catch (error) {
        message.error('获取指标列表失败：' + error.message)
      } finally {
        loading.value = false
      }
    }

    const fetchStatistics = async () => {
      try {
        const response = await api.get('/indicators/statistics')
        statistics.value = response
      } catch (error) {
        console.error('获取统计信息失败:', error)
      }
    }

    const fetchDocFilters = async () => {
      if (isPublic.value) return
      try {
        const response = await api.get('/public/docs/filters')
        docFilterOptions.years = response.years || []
        docFilterOptions.units = response.responsible_units || []
        docFilterOptions.departments = response.responsible_departments || []
      } catch (error) {
        console.error('获取文档筛选条件失败:', error)
      }
    }

    const fetchDocuments = async () => {
      if (isPublic.value) return
      docLoading.value = true
      try {
        const limit = 100
        const params = {
          limit,
          sort_by: 'publish_date',
          sort_dir: 'desc',
        }
        if (docFilters.year) params.year = docFilters.year
        if (docFilters.responsibleUnit) params.responsible_unit = docFilters.responsibleUnit
        if (docFilters.responsibleDepartment) params.responsible_department = docFilters.responsibleDepartment
        if (docFilters.keyword) params.keyword = docFilters.keyword
        let items = []
        let skip = 0
        let total = 0
        let page = 0
        const maxPages = 10
        do {
          const response = await api.get('/public/docs', {
            params: {
              ...params,
              skip,
            }
          })
          const pageItems = response.items || []
          total = response.total || 0
          items = items.concat(pageItems)
          skip += limit
          page += 1
          if (pageItems.length < limit) break
        } while (items.length < total && page < maxPages)

        const deduped = []
        const seen = new Set()
        items.forEach(item => {
          const pid = item.policy_id
          if (!pid || seen.has(pid)) return
          seen.add(pid)
          deduped.push(item)
        })
        documentMap.value = {}
        documentOptions.value = deduped.map(item => {
          const label = item.title || item.file_name || item.policy_id
          documentMap.value[item.policy_id] = item.doc_ids || []
          return {
            label,
            value: item.policy_id,
          }
        })
      } catch (error) {
        console.error('获取文档列表失败:', error)
      } finally {
        docLoading.value = false
      }
    }

    const applyDocFilters = () => {
      fetchDocuments()
    }

    const resetDocFilters = () => {
      docFilters.year = null
      docFilters.responsibleUnit = null
      docFilters.responsibleDepartment = null
      docFilters.keyword = ''
      fetchDocuments()
    }

    const selectAllDocs = () => {
      extractConfig.policyIds = documentOptions.value.map(item => item.value)
    }

    const clearDocSelection = () => {
      extractConfig.policyIds = []
    }

    const resolveSelectedDocIds = (policyIds) => {
      if (!policyIds || policyIds.length === 0) return []
      const docIds = []
      policyIds.forEach(pid => {
        const ids = documentMap.value[pid] || []
        ids.forEach(id => docIds.push(id))
      })
      return Array.from(new Set(docIds))
    }

    const searchIndicators = () => {
      pagination.current = 1
      fetchIndicators()
    }

    const resetFilters = () => {
      filters.year = null
      filters.primaryCategory = null
      filters.completionStatus = null
      filters.deadlineRange = null
      filters.responsibleUnit = ''
      filters.keyword = ''
      pagination.current = 1
      fetchIndicators()
    }

    const handleTableChange = (pag) => {
      pagination.current = pag.current
      pagination.pageSize = pag.pageSize
      fetchIndicators()
    }

    const applyBatchStatus = async (statusOverride) => {
      const ids = selectedRowKeys.value || []
      if (!ids.length) {
        message.warning('请先选择指标')
        return
      }
      const status = statusOverride || batchStatus.value
      try {
        const resp = await api.post('/indicators/status/batch', {
          indicator_ids: ids,
          status
        })
        message.success(`已更新 ${resp.updated || 0} 条指标`)
        selectedRowKeys.value = []
        fetchIndicators()
      } catch (error) {
        message.error('批量更新失败：' + error.message)
      }
    }

    const onSelectChange = (keys) => {
      selectedRowKeys.value = keys
    }

    const rowSelection = computed(() => {
      if (isPublic.value) return null
      return {
        selectedRowKeys: selectedRowKeys.value,
        onChange: onSelectChange
      }
    })

      const getStatusColor = (status) => {
        const colorMap = {
          '已完成': 'green',
          '进行中': 'orange',
          '部分完成': 'orange',
          '未启动': 'red',
          '待评估': 'blue',
          '无法判断': 'default'
        }
        return colorMap[status] || 'default'
      }

      const getStatusText = (status) => {
        const map = {
          '部分完成': '进行中',
          '未完成': '未启动'
        }
        return map[status] || status || '-'
      }

    const formatDate = (date) => {
      return date ? dayjs(date).format('YYYY-MM-DD') : '-'
    }

    const showExtractModal = () => {
      extractModalVisible.value = true
      fetchDocFilters()
      fetchDocuments()
    }

    const showImportModal = () => {
      message.info('请使用文件上传导入Excel')
    }

    const exportToExcel = async () => {
      try {
        const params = {}
        if (filters.year) params.year = filters.year
        if (filters.primaryCategory) params.primary_category = filters.primaryCategory
        if (filters.completionStatus) params.completion_status = filters.completionStatus
        if (filters.responsibleUnit) params.responsible_unit = filters.responsibleUnit
        if (filters.deadlineRange && filters.deadlineRange.length === 2) {
          params.deadline_from = dayjs(filters.deadlineRange[0]).format('YYYY-MM-DD')
          params.deadline_to = dayjs(filters.deadlineRange[1]).format('YYYY-MM-DD')
        }

        const response = await api.get('/indicators/export/excel', {
          params,
          responseType: 'blob',
        })
        const blob = response instanceof Blob ? response : new Blob([response])
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', `indicators_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`)
        document.body.appendChild(link)
        link.click()
        link.remove()
        
        message.success('导出成功')
      } catch (error) {
        message.error('导出失败：' + error.message)
      }
    }

    const handleExtract = async () => {
      extracting.value = true
      try {
        const response = await api.post('/indicators/extract', {
          policy_ids: extractConfig.policyIds,
          save_to_store: extractConfig.saveToStore,
        })
        
        message.success(`成功抽取 ${response.total_extracted} 条指标`)
        extractModalVisible.value = false
        fetchIndicators()
        fetchStatistics()
      } catch (error) {
        message.error('抽取失败：' + error.message)
      } finally {
        extracting.value = false
      }
    }

    const showAuditModal = () => {
      if (selectedRowKeys.value.length === 0) {
        message.warning('请先选择要审计的指标')
        return
      }
      auditModalVisible.value = true
    }

    const handleAudit = async () => {
      auditing.value = true
      try {
        const evidenceDocIds = resolveSelectedDocIds(auditConfig.policyIds)
        const response = await api.post('/indicators/audit', {
          indicator_ids: selectedRowKeys.value,
          evidence_doc_ids: evidenceDocIds.length > 0 ? evidenceDocIds : null,
          audit_focus: auditConfig.auditFocus || null,
        })
        
        const summary = response.summary
        message.success(
          `审计完成：达成 ${summary['达成']}，部分达成 ${summary['部分达成']}，` +
          `未达成 ${summary['未达成']}，无法判断 ${summary['无法判断']}`
        )
        auditModalVisible.value = false
        selectedRowKeys.value = []
        fetchIndicators()
        fetchStatistics()
      } catch (error) {
        message.error('审计失败：' + error.message)
      } finally {
        auditing.value = false
      }
    }

    const viewDetail = (record) => {
      currentIndicator.value = record
      detailModalVisible.value = true
    }

    const editIndicator = (_record) => {
      message.info('编辑功能开发中')
    }

    const deleteIndicator = async (id) => {
      try {
        await api.delete(`/indicators/${id}`)
        message.success('删除成功')
        fetchIndicators()
        fetchStatistics()
      } catch (error) {
        message.error('删除失败：' + error.message)
      }
    }

    // 初始化
    onMounted(() => {
      fetchIndicators()
      fetchStatistics()
      fetchDocFilters()
      fetchDocuments()
    })

      return {
        loading,
        indicators,
        selectedRowKeys,
        statistics,
        isPublic,
        isAdmin,
        isLeader,
        filters,
        pagination,
        batchStatus,
        columns,
        rowSelection,
      extractModalVisible,
      auditModalVisible,
      detailModalVisible,
      extracting,
      auditing,
      currentIndicator,
      extractConfig,
      auditConfig,
      docFilters,
      docFilterOptions,
      docLoading,
      documentOptions,
      availableYears,
      availableCategories,
      applyDocFilters,
      resetDocFilters,
      selectAllDocs,
      clearDocSelection,
        searchIndicators,
        resetFilters,
        handleTableChange,
        applyBatchStatus,
        onSelectChange,
      getStatusColor,
      getStatusText,
      formatTargetSource,
      formatDate,
      showExtractModal,
      showImportModal,
      exportToExcel,
      handleExtract,
      showAuditModal,
      handleAudit,
      viewDetail,
      editIndicator,
      deleteIndicator,
    }
  },
}
</script>

<style lang="less" scoped>
.indicators-container {
  height: 100%;
  padding: 16px;
  background: #f5f5f5;
}

.indicators-layout {
  display: flex;
  gap: 16px;
  height: 100%;
}

.filter-panel {
  width: 280px;
  flex-shrink: 0;
}

.main-panel {
  flex: 1;
  min-width: 0;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
}

.filter-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 16px;
}

.status-stats {
  .stat-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;

    .stat-label {
      color: #666;
    }
  }
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;

  .toolbar-left,
  .toolbar-right {
    display: flex;
    gap: 8px;
  }
}

.score-cell {
  font-weight: 600;
  color: #1890ff;
}

.scoring-rules {
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
}

.quote-text {
  color: #666;
  font-style: italic;
  font-size: 12px;
}
</style>

<template>
  <div class="file-ingest-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <div class="title-section">
          <h1 class="page-title">
            <upload-outlined class="title-icon" />
            文件入库
          </h1>
          <p class="page-description">
            上传政务文档，系统将自动提取部门、文号、日期等元数据信息
          </p>
        </div>
        
        <!-- 统计信息 -->
        <div class="stats-section">
          <a-row :gutter="16">
            <a-col :span="6">
              <a-statistic title="总文件数" :value="fileStats.total" />
            </a-col>
            <a-col :span="6">
              <a-statistic title="已上传" :value="fileStats.uploaded" />
            </a-col>
            <a-col :span="6">
              <a-statistic title="解析中" :value="fileStats.parsing" />
            </a-col>
            <a-col :span="6">
              <a-statistic 
                title="已完成" 
                :value="fileStats.completed"
                :value-style="{ color: '#3f8600' }"
              />
            </a-col>
          </a-row>
        </div>
      </div>
    </div>

    <div class="page-content">
      <a-row :gutter="16" align="stretch">
        <!-- 左侧：历史文件列表 -->
        <a-col :span="10">
          <a-card title="历史文件" class="file-list-card">
            <template #extra>
              <a-button 
                type="text" 
                size="small"
                @click="refreshFileList"
                :loading="refreshing"
              >
                <template #icon>
                  <reload-outlined />
                </template>
                刷新
              </a-button>
            </template>

            <!-- 搜索和筛选 -->
            <div class="search-filter-section">
              <a-input-search
                v-model:value="searchKeyword"
                placeholder="搜索文件名、部门..."
                @search="handleSearch"
                class="search-input"
              />
              
              <a-space class="filter-controls" size="small">
                <a-select
                  v-model:value="filterConditions.fileType"
                  placeholder="文件类型"
                  style="width: 100px"
                  allow-clear
                  @change="handleFilter"
                >
                  <a-select-option value="pdf">PDF</a-select-option>
                  <a-select-option value="docx,doc">Word</a-select-option>
                  <a-select-option value="xlsx,xls">Excel</a-select-option>
                </a-select>
                
                <a-select
                  v-model:value="filterConditions.parseStatus"
                  placeholder="解析状态"
                  style="width: 100px"
                  allow-clear
                  @change="handleFilter"
                >
                  <a-select-option value="completed">已完成</a-select-option>
                  <a-select-option value="parsing">解析中</a-select-option>
                  <a-select-option value="failed">失败</a-select-option>
                </a-select>
              </a-space>
            </div>

            <!-- 文件列表 -->
            <div class="file-list">
              <a-list
                :data-source="filteredFiles"
                :locale="{ emptyText: '暂无文件' }"
                class="file-list-content"
              >
                <template #renderItem="{ item }">
                  <a-list-item 
                    class="file-item"
                    :class="{ active: selectedFile?.id === item.id }"
                    @click="selectFile(item)"
                  >
                    <div class="file-info">
                      <div class="file-header">
                        <div class="file-icon">
                          <file-text-outlined v-if="item.name.endsWith('.pdf')" class="pdf-icon" />
                          <file-word-outlined v-else-if="item.name.includes('.doc')" class="word-icon" />
                          <file-excel-outlined v-else-if="item.name.includes('.xls')" class="excel-icon" />
                          <file-outlined v-else />
                        </div>
                        <div class="file-name" :title="item.name">
                          {{ item.name }}
                        </div>
                      </div>
                      
                      <div class="file-meta">
                        <div class="file-size">{{ formatFileSize(item.size) }}</div>
                        <div class="upload-time">{{ formatTime(item.uploadTime) }}</div>
                      </div>
                      
                      <div class="parse-status">
                        <a-tag 
                          :color="getStatusColor(item.parseStatus)"
                          class="status-tag"
                        >
                          {{ getStatusText(item.parseStatus) }}
                        </a-tag>
                        <a-tag color="blue" class="status-tag">
                          向量库：{{ getSyncStatusText(item.vectorStatus || 'success') }}
                        </a-tag>
                        <a-tag :color="getSyncStatusColor(item.relationStatus)" class="status-tag">
                          关系库：{{ getSyncStatusText(item.relationStatus) }}
                        </a-tag>
                      </div>
                    </div>
                    
                    <template #actions>
                      <a-button
                        v-if="isAdmin"
                        type="text"
                        size="small"
                        danger
                        @click.stop="deleteFile(item)"
                      >
                        <template #icon>
                          <delete-outlined />
                        </template>
                      </a-button>
                    </template>
                  </a-list-item>
                </template>
              </a-list>
            </div>
          </a-card>
        </a-col>

        <!-- 右侧：主工作区 -->
        <a-col :span="14">
          <div class="main-workspace">
            <!-- 上传区域 -->
            <a-card title="文件上传" class="upload-card">
              <div class="upload-section">
                <a-upload-dragger
                  name="file"
                  :multiple="true"
                  :file-list="uploadFileList"
                  :before-upload="beforeUpload"
                  @change="handleUploadChange"
                  @drop="handleDrop"
                  class="upload-dragger"
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.txt"
                >
                  <p class="ant-upload-drag-icon">
                    <inbox-outlined />
                  </p>
                  <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
                  <p class="ant-upload-hint">
                    支持 PDF、Word、Excel、TXT 格式，支持批量选择
                  </p>
                </a-upload-dragger>
                
                <!-- 上传配置 -->
                <div class="upload-config">
                  <a-row :gutter="16">
                    <a-col :span="8">
                      <a-form-item label="责任单位" name="department">
                        <a-select
                          v-model:value="uploadConfig.department"
                          allow-clear
                          show-search
                          placeholder="选择责任单位（可选）"
                        >
                          <a-select-option
                            v-for="unit in unitOptions"
                            :key="unit"
                            :value="unit"
                          >
                            {{ unit }}
                          </a-select-option>
                        </a-select>
                      </a-form-item>
                    </a-col>
                    <a-col :span="8">
                      <a-form-item label="文件年份" name="publishYear">
                        <a-select
                          v-model:value="uploadConfig.publishYear"
                          allow-clear
                          placeholder="选择年份（可选）"
                        >
                          <a-select-option
                            v-for="year in yearOptions"
                            :key="year"
                            :value="year"
                          >
                            {{ year }}年
                          </a-select-option>
                        </a-select>
                      </a-form-item>
                    </a-col>
                    <a-col :span="8">
                      <a-form-item label="提取元数据">
                        <a-switch
                          v-model:checked="uploadConfig.extractMetadata"
                          checked-children="开启"
                          un-checked-children="关闭"
                        />
                      </a-form-item>
                    </a-col>
                  </a-row>
                </div>

                <!-- 批量操作按钮 -->
                <div class="batch-actions">
                  <a-space>
                    <a-button
                      type="primary"
                      :loading="uploading"
                      :disabled="uploadFileList.length === 0"
                      @click="startUpload"
                    >
                      <template #icon>
                        <upload-outlined />
                      </template>
                      开始上传 ({{ uploadFileList.length }})
                    </a-button>
                    
                    <a-button
                      @click="clearUploadList"
                      :disabled="uploading || uploadFileList.length === 0"
                    >
                      清空列表
                    </a-button>
                    <a-button
                      v-if="canReconcile"
                      :loading="reconciling"
                      @click="reconcileFiles"
                    >
                      补偿同步
                    </a-button>
                  </a-space>
                </div>
              </div>
            </a-card>

            <!-- 解析状态面板 -->
            <a-card
              title="解析状态"
              class="parse-status-card"
              v-if="showParsePanel"
            >
              <template #extra>
                <a-button 
                  type="text" 
                  size="small"
                  @click="showParsePanel = false"
                >
                  <template #icon>
                    <close-outlined />
                  </template>
                </a-button>
              </template>

              <div class="parse-status-panel">
                <a-list
                  :data-source="recentUploads"
                  class="recent-uploads-list"
                >
                  <template #renderItem="{ item }">
                    <a-list-item class="upload-item">
                      <div class="item-content">
                        <div class="item-header">
                          <div class="file-name">{{ item.name }}</div>
                          <div class="item-actions">
                            <a-button
                              v-if="item.parseStatus === 'completed'"
                              type="link"
                              size="small"
                              @click="navigateToResult(item)"
                            >
                              查看结果
                            </a-button>
                          </div>
                        </div>
                        
                        <div class="item-meta">
                          <span class="upload-time">{{ formatTime(item.uploadTime) }}</span>
                          <a-divider type="vertical" />
                          <span class="file-size">{{ formatFileSize(item.size) }}</span>
                        </div>
                        <div class="sync-status-row">
                          <a-tag color="blue">向量库：{{ getSyncStatusText(item.vectorStatus || 'success') }}</a-tag>
                          <a-tag :color="getSyncStatusColor(item.relationStatus)">
                            关系库：{{ getSyncStatusText(item.relationStatus) }}
                          </a-tag>
                        </div>
                        
                        <div class="progress-section">
                          <div class="progress-header">
                            <span class="progress-label">
                              {{ getProgressLabel(item) }}
                            </span>
                            <span class="progress-percent">
                              {{ getProgressPercent(item) }}%
                            </span>
                          </div>
                          
                          <a-progress
                            :percent="getProgressPercent(item)"
                            :status="getProgressStatus(item)"
                            :show-info="false"
                            class="progress-bar"
                          />
                        </div>
                      </div>
                    </a-list-item>
                  </template>
                </a-list>
              </div>
            </a-card>
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { useStore } from 'vuex'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import api from '@/services/api'
import {
  UploadOutlined,
  InboxOutlined,
  FileTextOutlined,
  FileWordOutlined,
  FileExcelOutlined,
  FileOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CloseOutlined
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'

export default {
  name: 'FileIngest',
  components: {
    UploadOutlined,
    InboxOutlined,
    FileTextOutlined,
    FileWordOutlined,
    FileExcelOutlined,
    FileOutlined,
    DeleteOutlined,
    ReloadOutlined,
    CloseOutlined
  },
  setup() {
    const store = useStore()
    const router = useRouter()

    // 响应式数据
    const uploadFileList = ref([])
    const uploading = ref(false)
    const reconciling = ref(false)
    const refreshing = ref(false)
    const selectedFile = ref(null)
    const showParsePanel = ref(false)
    const searchKeyword = ref('')
    const filterConditions = ref({
      fileType: '',
      parseStatus: ''
    })
    
    const unitOptions = ref([])
    const yearOptions = ref([])

    // 上传配置
    const uploadConfig = ref({
      department: '',
      publishYear: null,
      extractMetadata: true
    })

    // 计算属性
    const files = computed(() => store.state.fileIngest.files)
    const isAdmin = computed(() => store.getters['auth/hasRole']('admin'))
    const canReconcile = computed(() => isAdmin.value || store.getters['auth/hasRole']('staff'))
    const fileStats = computed(() => store.getters['fileIngest/fileStats'])
    const filteredFiles = computed(() => store.getters['fileIngest/filteredFiles'])
    
    // 最近上传的文件（用于显示解析状态）
    const recentUploads = computed(() => {
      return files.value
        .filter(file => file.uploadTime)
        .sort((a, b) => new Date(b.uploadTime) - new Date(a.uploadTime))
        .slice(0, 10)
    })

    // 方法
    const formatFileSize = (bytes) => {
      if (bytes === 0) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    }

    const formatTime = (time) => {
      const d = dayjs(time)
      return d.isValid() ? d.format('MM-DD HH:mm') : '-'
    }

    const getStatusColor = (status) => {
      const colorMap = {
        pending: 'default',
        parsing: 'processing',
        completed: 'success',
        failed: 'error'
      }
      return colorMap[status] || 'default'
    }

    const getStatusText = (status) => {
      const textMap = {
        pending: '等待中',
        parsing: '解析中',
        completed: '已完成',
        failed: '失败'
      }
      return textMap[status] || '未知'
    }

    const getSyncStatusColor = (status) => {
      const colorMap = {
        success: 'success',
        partial_failed: 'warning',
        pending: 'default',
        disabled: 'default',
        failed: 'error'
      }
      return colorMap[status] || 'default'
    }

    const getSyncStatusText = (status) => {
      const textMap = {
        success: '已同步',
        partial_failed: '部分失败',
        pending: '待同步',
        disabled: '未启用',
        failed: '失败'
      }
      return textMap[status] || '未知'
    }

    const getProgressLabel = (item) => {
      const statusMap = {
        uploading: '上传中',
        parsing: '解析中',
        completed: '解析完成',
        failed: '解析失败'
      }
      return statusMap[item.status] || statusMap[item.parseStatus] || '处理中'
    }

    const getProgressPercent = (item) => {
      if (item.status === 'uploading') {
        return store.state.fileIngest.uploadProgress[item.id] || 0
      }
      if (item.parseStatus === 'parsing') {
        return 50
      }
      if (item.parseStatus === 'completed') {
        return 100
      }
      if (item.parseStatus === 'failed') {
        return 100
      }
      return 0
    }

    const getProgressStatus = (item) => {
      if (item.parseStatus === 'failed') return 'exception'
      if (item.parseStatus === 'completed') return 'success'
      return 'active'
    }

    // 工具函数：获取去除后缀的文件名
    const getFileNameWithoutExt = (fileName) => {
      if (!fileName) return ''
      const lastDot = fileName.lastIndexOf('.')
      return lastDot > 0 ? fileName.substring(0, lastDot) : fileName
    }

    // 检查是否存在同名文件（去除后缀比较）
    const checkDuplicateFile = (fileName) => {
      const baseName = getFileNameWithoutExt(fileName).toLowerCase()
      // 检查已入库文件列表
      const existingFile = files.value.find(f => {
        const existingBase = getFileNameWithoutExt(f.name).toLowerCase()
        return existingBase === baseName
      })
      if (existingFile) {
        return existingFile.name
      }
      // 检查当前待上传列表
      const pendingFile = uploadFileList.value.find(f => {
        const pendingBase = getFileNameWithoutExt(f.name).toLowerCase()
        return pendingBase === baseName && f.name !== fileName
      })
      if (pendingFile) {
        return pendingFile.name
      }
      return null
    }

    // 文件上传相关
    const beforeUpload = (file) => {
      const isValidType = /\.(pdf|docx?|xlsx?|txt)$/i.test(file.name)
      if (!isValidType) {
        message.error('只支持 PDF、Word、Excel、TXT 格式文件')
        return false
      }

      const isLt50M = file.size / 1024 / 1024 < 50
      if (!isLt50M) {
        message.error('文件大小不能超过 50MB')
        return false
      }

      // 检查同名文件（去除后缀比较，避免 pdf/docx 重复上传）
      const duplicateName = checkDuplicateFile(file.name)
      if (duplicateName) {
        message.warning(`已存在同名文件「${duplicateName}」，请勿重复上传`)
        return false
      }

      return false // 阻止自动上传
    }

    const handleUploadChange = ({ fileList }) => {
      uploadFileList.value = fileList
    }

    const handleDrop = (e) => {
      console.log('拖拽上传:', e.dataTransfer.files)
    }

    const startUpload = async () => {
      if (uploadFileList.value.length === 0) {
        message.warning('请先选择要上传的文件')
        return
      }

      uploading.value = true
      showParsePanel.value = true

      try {
        const files = uploadFileList.value.map(item => item.originFileObj)
        
        const results = await store.dispatch('fileIngest/batchUploadFiles', {
          files,
          options: {
            department: uploadConfig.value.department,
            publishYear: uploadConfig.value.publishYear,
            extractMetadata: uploadConfig.value.extractMetadata,
            onProgress: (progress) => {
              console.log('总体上传进度:', progress)
            }
          }
        })

        message.success('文件上传成功，正在解析中...')
        const partialCount = results.filter(item => item.relationStatus === 'partial_failed').length
        if (partialCount > 0) {
          message.warning(`已上传 ${results.length} 个文件，其中 ${partialCount} 个关系库同步失败，可点击补偿同步`)
        }
        uploadFileList.value = []
        
      } catch (error) {
        console.error('上传失败:', error)
        message.error('上传失败：' + error.message)
      } finally {
        uploading.value = false
      }
    }

    const clearUploadList = () => {
      uploadFileList.value = []
    }

    // 文件管理相关
    const reconcileFiles = async () => {
      reconciling.value = true
      try {
        const result = await store.dispatch('fileIngest/reconcileIngest', {
          department: uploadConfig.value.department,
          publishYear: uploadConfig.value.publishYear
        })
        if (result.sync_status === 'partial_failed') {
          message.warning('补偿同步部分失败：' + (result.sync_error || '请查看后端日志'))
        } else {
          message.success(`补偿同步完成，已同步 ${result.synced_count || 0} 条文档引用`)
        }
      } catch (error) {
        console.error('补偿同步失败:', error)
        message.error('补偿同步失败：' + error.message)
      } finally {
        reconciling.value = false
      }
    }

    const selectFile = (file) => {
      selectedFile.value = file
    }

    const deleteFile = async (fileId) => {
      try {
        await store.dispatch('fileIngest/deleteFile', fileId)
        message.success('文件删除成功')
        if (selectedFile.value?.id === fileId) {
          selectedFile.value = null
        }
      } catch (error) {
        console.error('删除文件失败:', error)
        message.error('删除失败：' + error.message)
      }
    }

    const refreshFileList = async () => {
      refreshing.value = true
      try {
        await store.dispatch('fileIngest/fetchFiles')
        message.success('刷新成功')
      } catch (error) {
        console.error('刷新失败:', error)
        message.error('刷新失败')
      } finally {
        refreshing.value = false
      }
    }

    // 搜索和筛选
    const handleSearch = () => {
      store.dispatch('fileIngest/searchFiles', searchKeyword.value)
    }

    const handleFilter = () => {
      store.dispatch('fileIngest/setFilterConditions', filterConditions.value)
    }

    const fetchIngestOptions = async () => {
      try {
        const response = await api.get('/public/docs/filters')
        unitOptions.value = response.responsible_units || []
        const currentYear = new Date().getFullYear()
        const years = new Set(response.years || [])
        for (let y = 2018; y <= currentYear + 1; y += 1) {
          years.add(y)
        }
        yearOptions.value = Array.from(years).sort((a, b) => b - a)
      } catch (error) {
        console.error('获取责任单位列表失败:', error)
        const currentYear = new Date().getFullYear()
        yearOptions.value = []
        for (let y = currentYear + 1; y >= 2018; y -= 1) {
          yearOptions.value.push(y)
        }
      }
    }

    // 导航到结果页面
    const navigateToResult = () => {
      // 根据文件类型导航到不同页面
      router.push('/chat')
    }

    // 监听搜索关键词变化
    watch(searchKeyword, (newKeyword) => {
      store.dispatch('fileIngest/searchFiles', newKeyword)
    })

    // 页面加载时获取文件列表
    onMounted(async () => {
      await fetchIngestOptions()
      await refreshFileList()
      // 若从聊天跳转携带查询参数，则尝试预选文件
      const { file, doc_id } = router.currentRoute.value.query || {}
      if (file || doc_id) {
        const target = files.value.find(f =>
          (file && f.name === file) ||
          (doc_id && Array.isArray(f.docIds) && f.docIds.includes(doc_id))
        )
        if (target) {
          selectedFile.value = target
        }
      }
    })

    return {
      // 响应式数据
      uploadFileList,
      uploading,
      reconciling,
      refreshing,
      selectedFile,
      showParsePanel,
      searchKeyword,
      filterConditions,
      uploadConfig,
      isAdmin,
      canReconcile,
      unitOptions,
      yearOptions,

      // 计算属性
      files,
      fileStats,
      filteredFiles,
      recentUploads,

      // 方法
      formatFileSize,
      formatTime,
      getStatusColor,
      getStatusText,
      getSyncStatusColor,
      getSyncStatusText,
      getProgressLabel,
      getProgressPercent,
      getProgressStatus,
      beforeUpload,
      handleUploadChange,
      handleDrop,
      startUpload,
      clearUploadList,
      reconcileFiles,
      selectFile,
      deleteFile,
      refreshFileList,
      handleSearch,
      handleFilter,
      navigateToResult
    }
  }
}
</script>

<style lang="less" scoped>
.file-ingest-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f0f2f5;
  overflow: hidden;
}

  .page-header {
  background: #fff;
  padding: 10px;
  border-bottom: 1px solid #f0f0f0;
  
  .header-content {
    width: 100%;
    margin: 0;
    
    .title-section {
      margin-bottom: 24px;
      
      .page-title {
        margin: 0 0 8px 0;
        font-size: 18px;
        font-weight: 500;
        color: #262626;
        display: flex;
        align-items: center;
        gap: 8px;
        
        .title-icon {
          color: #1890ff;
        }
      }
      
      .page-description {
        margin: 0;
        color: #8c8c8c;
        font-size: 14px;
      }
    }
    
    .stats-section {
      :deep(.ant-statistic) {
        text-align: center;
        
        .ant-statistic-title {
          font-size: 14px;
          color: #8c8c8c;
        }
        
        .ant-statistic-content {
          font-size: 24px;
          font-weight: 500;
        }
      }
    }
  }
}

.page-content {
  flex: 1;
  padding: 10px;
  width: 100%;
  margin: 0;
  overflow: auto;
}

// 左侧文件列表
.file-list-card {
  height: calc(100vh - 180px);
  display: flex;
  flex-direction: column;
  
  :deep(.ant-card-body) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 16px;
  }
  
  .search-filter-section {
    margin-bottom: 16px;
    
    .search-input {
      margin-bottom: 12px;
    }
    
    .filter-controls {
      width: 100%;
      justify-content: space-between;
    }
  }
  
  .file-list {
    flex: 1;
    min-height: 0;
    max-height: calc(100vh - 380px);
    overflow: hidden;
    
    .file-list-content {
      height: 100%;
      max-height: 100%;
      overflow-y: auto;
      overflow-x: hidden;
      
      .file-item {
        padding: 12px;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s;

        // 关键：允许内容区在 flex 容器内收缩，避免把 actions（删除键）挤出可视区
        :deep(.ant-list-item-main) {
          min-width: 0;
        }

        // 固定右侧 actions（删除键）布局，不随文件名变长而偏移/被挤出
        :deep(.ant-list-item-action) {
          flex: 0 0 auto;
          margin-left: 8px;
        }
        :deep(.ant-list-item-action > li) {
          padding: 0;
        }
        
        &:hover {
          background: #f5f5f5;
        }
        
        &.active {
          background: #e6f7ff;
          border: 1px solid #91d5ff;
        }
        
        .file-info {
          width: 100%;
          min-width: 0;
          
          .file-header {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            min-width: 0;
            
            .file-icon {
              margin-right: 8px;
              font-size: 16px;
              
              .pdf-icon { color: #ff4d4f; }
              .word-icon { color: #1890ff; }
              .excel-icon { color: #52c41a; }
            }
            
            .file-name {
              flex: 1;
              font-weight: 500;
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
            }
          }
          
          .file-meta {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 12px;
            color: #8c8c8c;
          }
          
          .parse-status {
            .status-tag {
              font-size: 12px;
            }
          }
        }
      }
    }
  }
}

// 右侧主工作区
.main-workspace {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100vh - 180px);
}

.upload-card {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
    .upload-section {
      margin-top: -8px;
    .upload-dragger {
      margin-bottom: 24px;
      
      :deep(.ant-upload-drag-container) {
        padding: 32px;
      }
    }
    
    .upload-config {
      margin-bottom: 24px;
      padding: 16px;
      background: #fafafa;
      border-radius: 6px;
    }
    
    .batch-actions {
      text-align: center;
    }
  }
  :deep(.ant-card-body) {
    flex: 1;
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    padding: 8px 16px 16px 16px;
  }
}

.parse-status-card {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  
  :deep(.ant-card-body) {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }
  
  .parse-status-panel {
    height: 100%;
    
    .recent-uploads-list {
      .upload-item {
        border: 1px solid #f0f0f0;
        border-radius: 6px;
        padding: 16px;
        margin-bottom: 12px;
        background: #fff;
        
        .item-content {
          width: 100%;
          
          .item-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            
            .file-name {
              font-weight: 500;
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
            }
          }
          
          .item-meta {
            font-size: 12px;
            color: #8c8c8c;
            margin-bottom: 12px;
          }

          .sync-status-row {
            margin-bottom: 10px;
          }
          
          .progress-section {
            .progress-header {
              display: flex;
              justify-content: space-between;
              margin-bottom: 8px;
              font-size: 14px;
              
              .progress-label {
                color: #595959;
              }
              
              .progress-percent {
                color: #1890ff;
                font-weight: 500;
              }
            }
            
            .progress-bar {
              :deep(.ant-progress-bg) {
                transition: all 0.3s ease;
              }
            }
          }
        }
      }
    }
  }
}

// 响应式设计
@media (max-width: 1200px) {
  .page-content {
    :deep(.ant-col-10) {
      flex: 0 0 40%;
      max-width: 40%;
    }
    
    :deep(.ant-col-14) {
      flex: 0 0 60%;
      max-width: 60%;
    }
  }
}

@media (max-width: 768px) {
  .page-content {
    :deep(.ant-col-8),
    :deep(.ant-col-16) {
      flex: 0 0 100%;
      max-width: 100%;
    }
  }
  
  .main-workspace {
    height: auto;
  }
  
  .file-list-card {
    height: 400px;
    margin-bottom: 24px;
  }
}
</style>

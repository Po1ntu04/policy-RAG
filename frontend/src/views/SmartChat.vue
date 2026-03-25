<template>
  <div class="smart-chat-container">
    <div class="chat-layout">
      <!-- 聊天主界面 -->
      <div class="chat-main">
        <!-- 聊天头部 -->
        <div class="chat-header">
          <div class="header-info">
            <div class="chat-title">
              <comment-outlined class="title-icon" />
              智能政务问答
            </div>
            <div class="chat-status">
              <a-badge 
                :status="getBadgeStatus()" 
                :text="getStatusText()"
              />
            </div>
          </div>
          
          <div class="header-actions">
            <a-tooltip title="上下文过滤">
              <a-button 
                type="text" 
                :icon="h(FilterOutlined)"
                @click="showContextFilter = true"
              />
            </a-tooltip>
            
            <a-tooltip title="清空对话">
              <a-button 
                type="text" 
                :icon="h(DeleteOutlined)"
                @click="handleClearChat"
              />
            </a-tooltip>
          </div>
        </div>
        <div v-if="focusDoc" class="focus-banner">
          <a-tag color="geekblue">当前聚焦</a-tag>
          <span class="focus-name">《{{ focusDoc.name }}》</span>
          <a-button type="link" size="small" @click="clearFocusDoc">清除</a-button>
        </div>

        <!-- 消息区域 -->
        <div class="chat-messages" ref="messagesContainer">
          <!-- 欢迎消息 -->
          <div v-if="messages.length === 0" class="welcome-message">
            <div class="welcome-content">
              <div class="welcome-icon">
                <robot-outlined />
              </div>
              <h3>欢迎使用智能政务问答系统</h3>
              <p>我可以帮助您：</p>
              <ul class="feature-list">
                <li><check-circle-outlined /> 查询政务文档信息</li>
                <li><check-circle-outlined /> 生成统计表格</li>
                <li><check-circle-outlined /> 进行审计评估</li>
                <li><check-circle-outlined /> 提供政策解读</li>
              </ul>
              
              <div class="quick-actions">
                <h4>快速开始：</h4>
                <div class="action-buttons">
                  <a-button 
                    v-for="suggestion in quickSuggestions" 
                    :key="suggestion.id"
                    type="dashed" 
                    size="small"
                    @click="handleQuickAction(suggestion.content)"
                    class="suggestion-btn"
                  >
                    {{ suggestion.content }}
                  </a-button>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 消息列表 -->
          <div 
            v-for="message in messages" 
            :key="message.id"
            class="message-wrapper"
            :class="{
              'user-message': message.role === 'user',
              'assistant-message': message.role === 'assistant',
              'system-message': message.role === 'system'
            }"
          >
            <div class="message-avatar">
              <a-avatar 
                v-if="message.role === 'user'"
                :icon="h(UserOutlined)"
                :style="{ backgroundColor: '#1890ff' }"
              />
              <a-avatar 
                v-else-if="message.role === 'assistant'"
                :icon="h(RobotOutlined)"
                :style="{ backgroundColor: '#52c41a' }"
              />
            </div>
            
            <div class="message-content">
              <div class="message-header">
                <span class="message-role">
                  {{ getRoleLabel(message.role) }}
                </span>
                <span class="message-time">
                  {{ formatTime(message.timestamp) }}
                </span>
              </div>
              
              <div class="message-text">
                <div v-if="message.status === 'typing'" class="typing-indicator">
                  <a-spin size="small" />
                  <span>正在思考中...</span>
                </div>
                
                <div v-else-if="message.status === 'failed'" class="error-message">
                  <exclamation-circle-outlined class="error-icon" />
                  <span>{{ message.content }}</span>
                  <a-button 
                    type="link" 
                    size="small"
                    @click="handleRetry"
                  >
                    重试
                  </a-button>
                </div>
                
                <div v-else>
                  <div 
                    class="message-body"
                    v-html="formatMessageContent(message.content)"
                  ></div>
                  
                  <!-- 来源信息 -->
                  <div v-if="message.sources && message.sources.length > 0" class="message-sources">
                    <div class="sources-header">
                      <file-text-outlined />
                      <span>参考文档 ({{ message.sources.length }})</span>
                    </div>
                    <div class="sources-list">
                      <a-tag 
                        v-for="(source, index) in getSortedSources(message).slice(0, 3)" 
                        :key="index"
                        color="blue"
                        class="source-tag"
                        @click="handleSourceClick(source)"
                      >
                        {{ getSourceName(source) }}
                      </a-tag>
                      <span v-if="message.sources.length > 3" class="more-sources">
                        +{{ message.sources.length - 3 }} 更多
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- 消息操作 -->
              <div v-if="message.role === 'assistant' && message.status === 'completed'" class="message-actions">
                <a-tooltip title="复制">
                  <a-button 
                    type="text" 
                    size="small"
                    :icon="h(CopyOutlined)"
                    @click="handleCopyMessage(message.content)"
                  />
                </a-tooltip>
                
                <a-tooltip title="重新生成">
                  <a-button 
                    type="text" 
                    size="small"
                    :icon="h(ReloadOutlined)"
                    @click="handleRegenerateResponse"
                  />
                </a-tooltip>
                
                <a-tooltip title="点赞">
                  <a-button 
                    type="text" 
                    size="small"
                    :icon="h(LikeOutlined)"
                    @click="handleLikeMessage(message.id)"
                  />
                </a-tooltip>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 输入区域 -->
        <div class="chat-input">
          <!-- 快捷功能栏 -->
          <div v-if="showQuickBar" class="quick-bar">
            <div class="quick-functions">
              <a-button 
                v-for="func in quickFunctions"
                :key="func.key"
                size="small"
                type="dashed"
                @click="handleQuickFunction(func)"
                class="quick-func-btn"
              >
                <component :is="func.icon" />
                {{ func.label }}
              </a-button>
            </div>
          </div>
          
          <!-- 主输入区 -->
          <div class="input-area">
            <div class="input-wrapper">
              <a-textarea
                v-model:value="currentInput"
                :rows="inputRows"
                :placeholder="inputPlaceholder"
                :disabled="!canSendMessage"
                @keydown="handleKeyDown"
                @focus="handleInputFocus"
                @blur="handleInputBlur"
                class="message-input"
                :auto-size="{ minRows: 1, maxRows: 6 }"
              />
              
              <!-- 输入工具栏 -->
              <div class="input-toolbar">
                <div class="toolbar-left">
                  <a-tooltip title="快捷功能">
                    <a-button 
                      type="text" 
                      size="small"
                      :icon="h(AppstoreOutlined)"
                      @click="showQuickBar = !showQuickBar"
                      :class="{ active: showQuickBar }"
                    />
                  </a-tooltip>
                  
                  <a-tooltip title="上传文件">
                    <a-button 
                      type="text" 
                      size="small"
                      :icon="h(PaperClipOutlined)"
                      @click="handleFileUpload"
                    />
                  </a-tooltip>
                </div>
                
                <div class="toolbar-right">
                  <span class="input-counter">
                    {{ currentInput.length }}/2000
                  </span>
                  
                  <a-button 
                    type="primary" 
                    :loading="isLoading"
                    :disabled="!currentInput.trim() || !canSendMessage"
                    @click="sendMessage"
                    class="send-button"
                    :icon="h(SendOutlined)"
                  >
                    发送
                  </a-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 右侧配置面板 -->
      <div class="chat-sidebar">
        <a-card title="对话设置" size="small">
          <div class="setting-item">
            <div class="setting-label">
              <bulb-outlined />
              智能功能
            </div>
            <a-switch
              v-model:checked="smartFeaturesEnabled"
              checked-children="开启"
              un-checked-children="关闭"
              @change="handleSmartFeaturesToggle"
            />
          </div>
          
          <div class="setting-item">
            <div class="setting-label">
              <link-outlined />
              显示来源
            </div>
            <a-switch
              v-model:checked="includeSources"
              checked-children="开启"
              un-checked-children="关闭"
              @change="handleSourcesToggle"
            />
          </div>
          
          <div class="setting-item">
            <div class="setting-label">
              <sound-outlined />
              语音输入
            </div>
            <a-switch
              v-model:checked="voiceEnabled"
              checked-children="开启"
              un-checked-children="关闭"
            />
          </div>
        </a-card>
        
        <!-- 对话历史 -->
        <a-card title="对话统计" size="small" class="chat-stats">
          <a-statistic
            title="消息数量"
            :value="userMessageCount"
            prefix="💬"
          />
          <a-divider size="small" />
          <a-statistic
            title="对话时长"
            :value="chatDuration"
            suffix="分钟"
            prefix="⏱️"
          />
        </a-card>
        
        <!-- 快捷操作 -->
        <a-card title="快捷操作" size="small" class="quick-actions">
          <a-space direction="vertical" style="width: 100%">
            <a-button block @click="exportChat" :icon="h(DownloadOutlined)">
              导出对话
            </a-button>
            <a-button block @click="clearChat" :icon="h(DeleteOutlined)">
              清空对话
            </a-button>
            <a-button block @click="regenerateResponse" :icon="h(ReloadOutlined)">
              重新生成
            </a-button>
          </a-space>
        </a-card>
      </div>
    </div>
    
    <!-- 上下文过滤弹窗 -->
    <a-modal
      v-model:open="showContextFilter"
      title="上下文过滤设置"
      @ok="applyContextFilter"
      width="500px"
    >
      <a-form layout="vertical">
        <a-form-item label="部门筛选">
          <a-select
            v-model:value="contextFilterForm.departments"
            mode="multiple"
            placeholder="选择部门"
            style="width: 100%"
            allow-clear
          >
            <a-select-option value="财政部">财政部</a-select-option>
            <a-select-option value="发改委">发改委</a-select-option>
            <a-select-option value="工信部">工信部</a-select-option>
          </a-select>
        </a-form-item>
        
        <a-form-item label="时间范围">
          <a-range-picker
            v-model:value="contextFilterForm.dateRange"
            style="width: 100%"
          />
        </a-form-item>
        
        <a-form-item label="文档类型">
          <a-checkbox-group v-model:value="contextFilterForm.documentTypes">
            <a-checkbox value="通知">通知</a-checkbox>
            <a-checkbox value="报告">报告</a-checkbox>
            <a-checkbox value="决议">决议</a-checkbox>
            <a-checkbox value="规定">规定</a-checkbox>
          </a-checkbox-group>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script>
import { ref, computed, onMounted, nextTick, h, reactive, watch } from 'vue'
import { useStore } from 'vuex'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  CommentOutlined,
  FilterOutlined,
  DeleteOutlined,
  RobotOutlined,
  UserOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  CopyOutlined,
  ReloadOutlined,
  LikeOutlined,
  AppstoreOutlined,
  PaperClipOutlined,
  SendOutlined,
  BulbOutlined,
  LinkOutlined,
  SoundOutlined,
  DownloadOutlined,
  TableOutlined,
  AuditOutlined
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'

export default {
  name: 'SmartChat',
  components: {
    CommentOutlined,
    FilterOutlined,
    DeleteOutlined,
    RobotOutlined,
    UserOutlined,
    CheckCircleOutlined,
    ExclamationCircleOutlined,
    FileTextOutlined,
    CopyOutlined,
    ReloadOutlined,
    LikeOutlined,
    AppstoreOutlined,
    PaperClipOutlined,
    SendOutlined,
    BulbOutlined,
    LinkOutlined,
    SoundOutlined,
    DownloadOutlined,
    TableOutlined,
    AuditOutlined
  },
  setup() {
    const store = useStore()
    const router = useRouter()
    const route = useRoute()
    const messagesContainer = ref(null)
    const currentInput = ref('')
    
    // 界面状态
    const showContextFilter = ref(false)
    const showQuickBar = ref(false)
    const inputRows = ref(1)
    const voiceEnabled = ref(false)
    const chatStartTime = ref(Date.now())
    const focusDoc = ref(null)
    
    // 上下文过滤表单
    const contextFilterForm = reactive({
      departments: [],
      dateRange: null,
      documentTypes: []
    })

    // 计算属性
    const messages = computed(() => store.state.chat.messages)
    const isLoading = computed(() => store.getters['chat/isLoading'])
    const canSendMessage = computed(() => store.getters['chat/canSendMessage'])
    const userMessageCount = computed(() => store.getters['chat/userMessageCount'])
    const smartFeaturesEnabled = computed({
      get: () => store.state.chat.smartFeaturesEnabled,
      set: (value) => store.commit('chat/SET_SMART_FEATURES', value)
    })
    const includeSources = computed({
      get: () => store.state.chat.includeSources,
      set: (value) => store.commit('chat/SET_INCLUDE_SOURCES', value)
    })
    const isPublic = computed(() => store.getters['auth/isPublic'])
    const inputPlaceholder = computed(() => {
      if (focusDoc.value?.name) {
        return `针对《${focusDoc.value.name}》进行提问...`
      }
      return '请输入您的问题，支持智能识别表格生成、审计评价等需求...'
    })
    
    const chatDuration = computed(() => {
      return Math.floor((Date.now() - chatStartTime.value) / 1000 / 60)
    })
    
    // 快速建议
    const quickSuggestions = ref([
      { id: 1, content: '生成各部门预算执行情况表格' },
      { id: 2, content: '对财政文件进行合规性审计' },
      { id: 3, content: '查询最新的政策文件' },
      { id: 4, content: '统计各部门项目完成情况' }
    ])
    
    // 快捷功能
    const quickFunctions = ref([
      { key: 'table', label: '表格生成', icon: TableOutlined },
      { key: 'audit', label: '审计评估', icon: AuditOutlined },
      { key: 'search', label: '文档搜索', icon: FileTextOutlined }
    ])

    // 方法
    const formatTime = (timestamp) => {
      return dayjs(timestamp).format('HH:mm')
    }

    const formatMessageContent = (content) => {
      if (!content) return ''
      return content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>')
    }
    
    const getRoleLabel = (role) => {
      const roleMap = {
        user: '您',
        assistant: '智能助手',
        system: '系统'
      }
      return roleMap[role] || role
    }
    
    const getBadgeStatus = () => {
      if (isLoading.value) return 'processing'
      if (messages.value.length > 0) return 'success'
      return 'default'
    }
    
    const getStatusText = () => {
      if (isLoading.value) return '思考中'
      if (messages.value.length > 0) return '在线'
      return '等待输入'
    }

    const applyDocFocusFromRoute = () => {
      const docId = String(route.query?.doc_id || '').trim()
      if (!docId) {
        focusDoc.value = null
        store.dispatch('chat/setContextFilter', null)
        store.dispatch('chat/clearSystemPrompt')
        return
      }
      const docName = String(route.query?.doc_name || '选定文件')
      focusDoc.value = { id: docId, name: docName }
      store.dispatch('chat/setContextFilter', { docs_ids: [docId] })
      store.dispatch(
        'chat/setSystemPrompt',
        `你是政务问答助手。当前仅可使用文档《${docName}》回答问题，避免引用其他文件。`
      )
    }

    const clearFocusDoc = () => {
      focusDoc.value = null
      store.dispatch('chat/setContextFilter', null)
      store.dispatch('chat/clearSystemPrompt')
      router.replace({ path: '/chat' })
    }
    
    const getSourceName = (source) => {
      if (source?.document?.doc_metadata?.file_name) {
        return source.document.doc_metadata.file_name
      }
      return '参考文档'
    }

      const getSortedSources = (message) => {
        const sources = Array.isArray(message?.sources) ? message.sources : []
        return sources.slice().sort((a, b) => ((b?.score ?? 0) - (a?.score ?? 0)))
      }

    const scrollToBottom = () => {
      nextTick(() => {
        if (messagesContainer.value) {
          messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
        }
      })
    }

    const sendMessage = async () => {
      if (!currentInput.value.trim()) return

      try {
        await store.dispatch('chat/sendMessage', {
          content: currentInput.value.trim(),
          type: 'text'
        })
        currentInput.value = ''
        showQuickBar.value = false
        scrollToBottom()
      } catch (error) {
        message.error('发送消息失败：' + error.message)
      }
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        sendMessage()
      }
    }
    
    const handleInputFocus = () => {
      inputRows.value = 2
    }
    
    const handleInputBlur = () => {
      if (!currentInput.value.trim()) {
        inputRows.value = 1
      }
    }
    
    const handleQuickAction = (content) => {
      currentInput.value = content
      sendMessage()
    }
    
    const handleQuickFunction = (func) => {
      switch (func.key) {
        case 'table':
          currentInput.value = '请帮我生成一个表格，'
          break
        case 'audit':
          currentInput.value = '请对文档进行审计评估，'
          break
        case 'search':
          currentInput.value = '请帮我搜索相关文档，'
          break
      }
      // 聚焦到输入框
      nextTick(() => {
        const textarea = document.querySelector('.message-input textarea')
        if (textarea) {
          textarea.focus()
          textarea.setSelectionRange(textarea.value.length, textarea.value.length)
        }
      })
    }
    
    const handleFileUpload = () => {
      if (isPublic.value) {
        message.warning('公开用户无权限上传文件')
        router.push('/public-docs')
        return
      }
      router.push('/ingest')
    }
    
    const handleCopyMessage = async (content) => {
      try {
        await navigator.clipboard.writeText(content.replace(/<[^>]*>/g, ''))
        message.success('已复制到剪贴板')
      } catch (error) {
        message.error('复制失败')
      }
    }
    
    const handleLikeMessage = (messageId) => {
      void messageId
      message.success('感谢您的反馈')
    }
    
    const handleRetry = () => {
      regenerateResponse()
    }
    
    const handleSourceClick = (source) => {
      const fileName = source?.document?.doc_metadata?.file_name || null
      const docId = source?.document?.doc_id || null
      const page = source?.document?.doc_metadata?.page_label || null

      router.push({
        path: '/ingest',
        query: {
          ...(fileName ? { file: fileName } : {}),
          ...(docId ? { doc_id: docId } : {}),
          ...(page ? { page } : {})
        }
      })
    }

    const clearChat = () => {
      store.dispatch('chat/clearChat')
      chatStartTime.value = Date.now()
    }

    const regenerateResponse = () => {
      store.dispatch('chat/regenerateResponse')
    }
    
    const exportChat = () => {
      const chatData = {
        messages: messages.value,
        timestamp: new Date().toISOString(),
        messageCount: messages.value.length
      }
      
      const blob = new Blob([JSON.stringify(chatData, null, 2)], {
        type: 'application/json'
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `chat-export-${dayjs().format('YYYYMMDD-HHmmss')}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      
      message.success('对话已导出')
    }

    const handleSmartFeaturesToggle = (checked) => {
      void checked
      store.dispatch('chat/toggleSmartFeatures')
    }

    const handleSourcesToggle = (checked) => {
      void checked
      store.dispatch('chat/toggleIncludeSources')
    }
    
    const handleClearChat = () => {
      clearChat()
    }
    
    const applyContextFilter = () => {
      const filter = {
        departments: contextFilterForm.departments.length > 0 ? contextFilterForm.departments : null,
        dateRange: contextFilterForm.dateRange ? [
          contextFilterForm.dateRange[0].format('YYYY-MM-DD'),
          contextFilterForm.dateRange[1].format('YYYY-MM-DD')
        ] : null,
        documentTypes: contextFilterForm.documentTypes.length > 0 ? contextFilterForm.documentTypes : null
      }
      
      store.dispatch('chat/setContextFilter', filter)
      showContextFilter.value = false
      message.success('上下文过滤设置已应用')
    }

    watch(
      () => [route.query?.doc_id, route.query?.doc_name],
      () => applyDocFocusFromRoute()
    )

    onMounted(() => {
      scrollToBottom()
      applyDocFocusFromRoute()
    })

    return {
      h,
      messagesContainer,
      currentInput,
      showContextFilter,
      showQuickBar,
      inputRows,
      voiceEnabled,
      contextFilterForm,
      messages,
      isLoading,
      canSendMessage,
      userMessageCount,
      smartFeaturesEnabled,
      includeSources,
      chatDuration,
      focusDoc,
      inputPlaceholder,
      quickSuggestions,
      quickFunctions,
      formatTime,
      formatMessageContent,
      getRoleLabel,
      getBadgeStatus,
      getStatusText,
      getSourceName,
        getSortedSources,
      clearFocusDoc,
      sendMessage,
      handleKeyDown,
      handleInputFocus,
      handleInputBlur,
      handleQuickAction,
      handleQuickFunction,
      handleFileUpload,
      handleCopyMessage,
      handleLikeMessage,
      handleRetry,
      handleSourceClick,
      clearChat,
      regenerateResponse,
      exportChat,
      handleSmartFeaturesToggle,
      handleSourcesToggle,
      handleClearChat,
      applyContextFilter
    }
  }
}
</script>

<style lang="less" scoped>
.smart-chat-container {
  height: calc(100vh - 64px);
  background: #f0f2f5;
  display: flex;
  flex-direction: column;
}

.chat-layout {
  height: 100%;
  display: flex;
  padding: 0;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  margin: 16px;
  margin-right: 8px;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.chat-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fafafa;
  
  .header-info {
    display: flex;
    align-items: center;
    gap: 16px;
    
    .chat-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 500;
      color: #262626;
      
      .title-icon {
        color: #1890ff;
        font-size: 18px;
      }
    }
  }
  
  .header-actions {
    display: flex;
    gap: 4px;
  }
}

.focus-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid #f0f0f0;
  background: #f7faff;

  .focus-name {
    color: #1f1f1f;
    font-weight: 500;
  }
}

.chat-messages {
  flex: 1;
  padding: 16px 20px;
  overflow-y: auto;
  background: #f8f9fa;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: #c1c1c1;
    border-radius: 3px;
    
    &:hover {
      background: #a8a8a8;
    }
  }
}

.welcome-message {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  
  .welcome-content {
    text-align: center;
    max-width: 500px;
    
    .welcome-icon {
      font-size: 64px;
      color: #52c41a;
      margin-bottom: 24px;
    }
    
    h3 {
      color: #262626;
      font-size: 20px;
      font-weight: 500;
      margin-bottom: 16px;
    }
    
    p {
      color: #8c8c8c;
      font-size: 14px;
      margin-bottom: 20px;
    }
    
    .feature-list {
      text-align: left;
      list-style: none;
      padding: 0;
      margin: 0 0 32px 0;
      
      li {
        padding: 8px 0;
        color: #595959;
        display: flex;
        align-items: center;
        gap: 8px;
        
        .anticon {
          color: #52c41a;
        }
      }
    }
    
    .quick-actions {
      h4 {
        font-size: 16px;
        color: #262626;
        margin-bottom: 16px;
      }
      
      .action-buttons {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: center;
        
        .suggestion-btn {
          border-radius: 16px;
          border-color: #d9d9d9;
          
          &:hover {
            border-color: #40a9ff;
            color: #40a9ff;
          }
        }
      }
    }
  }
}

.message-wrapper {
  margin-bottom: 24px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  
  &.user-message {
    flex-direction: row-reverse;
    
    .message-content {
      background: linear-gradient(135deg, #1890ff 0%, #40a9ff 100%);
      color: white;
      border-radius: 18px 18px 4px 18px;
      max-width: 70%;
      
      .message-header {
        .message-role {
          color: rgba(255, 255, 255, 0.8);
        }
        
        .message-time {
          color: rgba(255, 255, 255, 0.6);
        }
      }
    }
  }
  
  &.assistant-message {
    .message-content {
      background: #fff;
      border: 1px solid #f0f0f0;
      border-radius: 18px 18px 18px 4px;
      max-width: 80%;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
  }
  
  .message-avatar {
    flex-shrink: 0;
    margin-top: 4px;
  }
  
  .message-content {
    padding: 12px 16px;
    position: relative;
    
    .message-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      font-size: 12px;
      
      .message-role {
        font-weight: 500;
        opacity: 0.8;
      }
      
      .message-time {
        opacity: 0.6;
      }
    }
    
    .message-text {
      .message-body {
        line-height: 1.6;
        word-break: break-word;
        font-size: 14px;
        
        :deep(strong) {
          font-weight: 600;
        }
        
        :deep(em) {
          font-style: italic;
          color: #1890ff;
        }
        
        :deep(code) {
          background: rgba(0,0,0,0.06);
          padding: 2px 4px;
          border-radius: 3px;
          font-family: 'Consolas', 'Monaco', monospace;
          font-size: 12px;
        }
      }
      
      .typing-indicator {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #8c8c8c;
        font-style: italic;
      }
      
      .error-message {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #ff4d4f;
        
        .error-icon {
          color: #ff7875;
        }
      }
      
      .message-sources {
        margin-top: 12px;
        padding-top: 12px;
        border-top: 1px solid #f0f0f0;
        
        .sources-header {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: #8c8c8c;
          margin-bottom: 8px;
        }
        
        .sources-list {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          align-items: center;
          
          .source-tag {
            cursor: pointer;
            font-size: 11px;
            
            &:hover {
              opacity: 0.8;
            }
          }
          
          .more-sources {
            font-size: 11px;
            color: #8c8c8c;
          }
        }
      }
    }
    
    .message-actions {
      position: absolute;
      top: 8px;
      right: 8px;
      opacity: 0;
      transition: opacity 0.2s;
      display: flex;
      gap: 2px;
    }
    
    &:hover .message-actions {
      opacity: 1;
    }
  }
}

.chat-input {
  background: #fff;
  border-top: 1px solid #f0f0f0;
  
  .quick-bar {
    padding: 12px 20px;
    border-bottom: 1px solid #f0f0f0;
    background: #fafafa;
    
    .quick-functions {
      display: flex;
      gap: 8px;
      
      .quick-func-btn {
        display: flex;
        align-items: center;
        gap: 4px;
        border-radius: 16px;
        font-size: 12px;
        
        .anticon {
          font-size: 14px;
        }
      }
    }
  }
  
  .input-area {
    padding: 16px 20px;
    
    .input-wrapper {
      border: 1px solid #d9d9d9;
      border-radius: 8px;
      overflow: hidden;
      transition: border-color 0.3s;
      
      &:focus-within {
        border-color: #40a9ff;
        box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
      }
      
      .message-input {
        border: none;
        resize: none;
        
        :deep(textarea) {
          border: none !important;
          box-shadow: none !important;
          padding: 12px 16px 8px 16px !important;
          font-size: 14px;
          line-height: 1.5;
          
          &:focus {
            border: none !important;
            box-shadow: none !important;
          }
          
          &::placeholder {
            color: #bfbfbf;
          }
        }
      }
      
      .input-toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        background: #fafafa;
        border-top: 1px solid #f0f0f0;
        
        .toolbar-left {
          display: flex;
          gap: 4px;
          
          .ant-btn.active {
            color: #1890ff;
            background: rgba(24, 144, 255, 0.1);
          }
        }
        
        .toolbar-right {
          display: flex;
          align-items: center;
          gap: 12px;
          
          .input-counter {
            font-size: 12px;
            color: #8c8c8c;
          }
          
          .send-button {
            border-radius: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
          }
        }
      }
    }
  }
}

.chat-sidebar {
  width: 280px;
  padding: 16px;
  padding-left: 8px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #f0f2f5;
  
  .ant-card {
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    
    :deep(.ant-card-head) {
      padding: 12px 16px;
      min-height: auto;
      
      .ant-card-head-title {
        font-size: 14px;
        font-weight: 500;
      }
    }
    
    :deep(.ant-card-body) {
      padding: 16px;
    }
  }
  
  .setting-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    
    &:last-child {
      margin-bottom: 0;
    }
    
    .setting-label {
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 500;
      font-size: 13px;
      color: #595959;
      
      .anticon {
        font-size: 14px;
        color: #8c8c8c;
      }
    }
  }
  
  .chat-stats {
    .ant-statistic {
      text-align: center;
      
      :deep(.ant-statistic-title) {
        color: #8c8c8c;
        font-size: 12px;
      }
      
      :deep(.ant-statistic-content) {
        font-size: 18px;
        font-weight: 500;
      }
    }
  }
  
  .quick-actions {
    margin-top: auto;
    
    .ant-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      height: 36px;
      border-radius: 6px;
      font-size: 13px;
    }
  }
}

// 响应式设计
@media (max-width: 1200px) {
  .chat-sidebar {
    width: 260px;
  }
  
  .message-wrapper {
    &.user-message .message-content,
    &.assistant-message .message-content {
      max-width: 85%;
    }
  }
}

@media (max-width: 768px) {
  .chat-layout {
    flex-direction: column;
    padding: 8px;
  }
  
  .chat-main {
    margin: 0 0 8px 0;
  }
  
  .chat-sidebar {
    width: 100%;
    padding: 8px;
    flex-direction: row;
    gap: 8px;
    overflow-x: auto;
    
    .ant-card {
      min-width: 200px;
      flex-shrink: 0;
    }
  }
  
  .message-wrapper {
    .message-content {
      max-width: 90% !important;
    }
    
    .message-actions {
      position: relative;
      opacity: 1;
      top: auto;
      right: auto;
      margin-top: 8px;
      justify-content: center;
    }
  }
  
  .chat-input .input-area {
    padding: 12px 16px;
  }
}

// 动画效果
.message-wrapper {
  animation: fadeInUp 0.3s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

// 自定义滚动条
.chat-messages::-webkit-scrollbar {
  width: 6px;
}

.chat-messages::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.chat-messages::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.chat-messages::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>

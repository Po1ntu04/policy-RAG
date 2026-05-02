import axios from 'axios'

// 从环境变量读取 API 地址，支持开发和生产环境配置
// 开发环境在 .env.development 中配置 VITE_API_BASE=http://localhost:8001/v1
// 生产环境在 .env.production 中配置对应地址
const API_BASE_URL = import.meta.env?.VITE_API_BASE
  || process.env.VUE_APP_API_BASE
  || 'http://localhost:8001/v1'

// 创建axios实例
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    // 后端使用 Basic 认证，secret 配置在 settings.yaml 的 server.auth.secret
    // 前端可通过 localStorage 存储 secret，或通过环境变量配置
    const authToken = localStorage.getItem('auth_token')
    if (authToken) {
      config.headers.Authorization = `Bearer ${authToken}`
      return config
    }

    const authSecret = localStorage.getItem('auth_secret')
      || import.meta.env?.VITE_AUTH_SECRET
      || process.env.VUE_APP_AUTH_SECRET

    if (authSecret) {
      const credentials = btoa(':' + authSecret)
      config.headers.Authorization = `Basic ${credentials}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    console.error('API Error:', error)

    if (error.response) {
      const { status, data } = error.response

      if (status === 401) {
        // 未授权，可能需要重新登录
        localStorage.removeItem('auth_token')
        localStorage.removeItem('auth_user')
        window.location.href = '/login'
      }

      throw new Error(data?.detail || `HTTP ${status} Error`)
    } else if (error.request) {
      const cfg = error.config || {}
      const base = cfg.baseURL || ''
      const url = cfg.url || ''
      const method = (cfg.method || 'GET').toUpperCase()
      const full = `${base}${url}`
      throw new Error(`网络连接失败，请检查后端是否可访问或 CORS/防火墙限制（${method} ${full}）`)
    } else {
      throw new Error(error.message || '未知错误')
    }
  }
)

// 文件上传辅助函数
const createFormData = (file, data = {}) => {
  const formData = new FormData()
  formData.append('file', file)

  Object.keys(data).forEach(key => {
    if (data[key] !== undefined && data[key] !== null) {
      formData.append(key, data[key])
    }
  })

  return formData
}

// 政务文件摄取API
export const governmentAPI = {
  // 单文件摄取
  async ingestFile(file, options = {}) {
    const formData = createFormData(file, {
      extract_metadata: options.extractMetadata ?? true,
      department: options.department
    })

    return api.post('/government/ingest/file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: options.onProgress
    })
  },

  // 批量文件摄取
  async bulkIngestFiles(files, options = {}) {
    const formData = new FormData()
    files.forEach(file => {
      formData.append('files', file)
    })
    formData.append('extract_metadata', options.extractMetadata ?? true)

    return api.post('/government/ingest/bulk', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: options.onProgress
    })
  },

  // 智能对话
  async chat(messages, options = {}) {
    return api.post('/government/chat/completions', {
      messages,
      use_context: options.useContext ?? true,
      context_filter: options.contextFilter,
      enable_smart_features: options.enableSmartFeatures ?? true,
      include_sources: options.includeSources ?? true,
      stream: options.stream ?? false
    })
  },

  // 生成表格
  async generateTable(request) {
    return api.post('/government/table/generate', {
      query: request.query,
      columns: request.columns,
      context_filter: request.contextFilter,
      max_rows: request.maxRows || 100,
      table_description: request.tableDescription
    })
  },

  // 执行审计
  async conductAudit(request) {
    return api.post('/government/audit/conduct', {
      audit_type: request.auditType,
      target_query: request.targetQuery,
      context_filter: request.contextFilter,
      audit_rules: request.auditRules,
      include_recommendations: request.includeRecommendations ?? true,
      detailed_analysis: request.detailedAnalysis ?? true
    })
  },

  // 获取审计规则
  async getAuditRules() {
    return api.get('/government/audit/rules')
  },

  // 提取元数据
  async extractMetadata(request) {
    return api.post('/government/metadata/extract', {
      query: request.query,
      context_filter: request.contextFilter,
      limit: request.limit || 10
    })
  },

  // 获取配置
  async getConfig() {
    return api.get('/government/config')
  }
}

// 通用摄取API
export const ingestAPI = {
  // 摄取文件
  async ingestFile(file, options = {}) {
    const formData = createFormData(file, {
      department: options.department,
      publish_year: options.publishYear
    })

    return api.post('/ingest/file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      onUploadProgress: options.onProgress
    })
  },

  // 获取摄取状态
  async getIngestStatus() {
    // 后端实际提供的是 /ingest/list
    return api.get('/ingest/list')
  },

  // 删除文档
  async deleteDocument(docId) {
    return api.delete(`/ingest/${docId}`)
  },

  async reconcile(options = {}) {
    return api.post('/ingest/reconcile', {
      department: options.department || null,
      publish_year: options.publishYear || null
    })
  }
}

// 聊天API
export const chatAPI = {
  // 聊天完成
  async completions(messages, options = {}) {
    return api.post('/chat/completions', {
      messages,
      use_context: options.useContext ?? true,
      context_filter: options.contextFilter,
      include_sources: options.includeSources ?? true,
      stream: options.stream ?? false,
      system_prompt: options.systemPrompt || null,
      use_default_prompt: options.useDefaultPrompt ?? true
    })
  }
}

// 文档块API
export const chunksAPI = {
  // 检索相关文档块
  async retrieve(text, options = {}) {
    return api.post('/chunks', {
      text,
      context_filter: options.contextFilter,
      limit: options.limit || 10
    })
  }
}

// 健康检查API
export const healthAPI = {
  async check() {
    return api.get('/health')
  }
}

// 导出默认API实例
export default api

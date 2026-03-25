import { ingestAPI } from '../../services/api'

export default {
  namespaced: true,
  state: {
    // 文件列表
    files: [],
    // 上传进度映射
    uploadProgress: {},
    // 解析状态映射
    parseStatus: {},
    // 搜索关键词
    searchKeyword: '',
    // 筛选条件
    filterConditions: {
      fileType: '',
      uploadDate: null,
      parseStatus: ''
    }
  },
  mutations: {
    // 设置文件列表
    SET_FILES(state, files) {
      state.files = files
    },
    // 添加文件
    ADD_FILE(state, file) {
      state.files.unshift(file)
    },
    // 更新文件
    UPDATE_FILE(state, { fileId, updates }) {
      const index = state.files.findIndex(f => f.id === fileId)
      if (index !== -1) {
        state.files[index] = { ...state.files[index], ...updates }
      }
    },
    // 删除文件
    REMOVE_FILE(state, fileId) {
      state.files = state.files.filter(f => f.id !== fileId)
    },
    // 设置上传进度
    SET_UPLOAD_PROGRESS(state, { fileId, progress }) {
      state.uploadProgress = {
        ...state.uploadProgress,
        [fileId]: progress
      }
    },
    // 清除上传进度
    CLEAR_UPLOAD_PROGRESS(state, fileId) {
      const rest = { ...state.uploadProgress }
      delete rest[fileId]
      state.uploadProgress = rest
    },
    // 设置解析状态
    SET_PARSE_STATUS(state, { fileId, status }) {
      state.parseStatus = {
        ...state.parseStatus,
        [fileId]: status
      }
    },
    // 设置搜索关键词
    SET_SEARCH_KEYWORD(state, keyword) {
      state.searchKeyword = keyword
    },
    // 设置筛选条件
    SET_FILTER_CONDITIONS(state, conditions) {
      state.filterConditions = { ...state.filterConditions, ...conditions }
    },
    // 重置筛选条件
    RESET_FILTER_CONDITIONS(state) {
      state.filterConditions = {
        fileType: '',
        uploadDate: null,
        parseStatus: ''
      }
    }
  },
  actions: {
    // 获取文件列表
    async fetchFiles({ commit }) {
      try {
        const result = await ingestAPI.getIngestStatus()
        const rawDocs = result?.data || []

        // 将相同 file_name 的文档聚合为一条
        const groupMap = new Map()
        for (const doc of rawDocs) {
          const fileName = doc?.doc_metadata?.file_name || doc.doc_id
          const createdAt = doc?.doc_metadata?.created_at || null
          const fileSize = doc?.doc_metadata?.file_size || 0
          if (!groupMap.has(fileName)) {
            groupMap.set(fileName, {
              id: fileName, // 使用文件名作为分组后的稳定ID
              name: fileName,
              size: fileSize,
              uploadTime: createdAt,
              status: 'uploaded',
              parseStatus: 'completed',
              metadata: {},
              docIds: [doc.doc_id]
            })
          } else {
            const item = groupMap.get(fileName)
            item.docIds.push(doc.doc_id)
            // 取最大/最新的时间与最大文件大小（如果后端提供）
            item.uploadTime = item.uploadTime || createdAt
            item.size = Math.max(item.size || 0, fileSize || 0)
          }
        }
        const files = Array.from(groupMap.values())
        commit('SET_FILES', files)
        return files
      } catch (error) {
        console.error('获取文件列表失败:', error)
        throw error
      }
    },
    
    // 上传单个文件（政务功能）
    async uploadFile({ commit }, { file, options = {} }) {
      try {
        // 创建临时文件记录
        const tempFile = {
          id: Date.now() + Math.random(),
          name: file.name,
          size: file.size,
          type: file.type,
          uploadTime: new Date().toISOString(),
          status: 'uploading',
          parseStatus: 'pending'
        }
        
        commit('ADD_FILE', tempFile)
        
        // 使用通用摄取API上传文件
        const result = await ingestAPI.ingestFile(file, {
          department: options.department,
          publishYear: options.publishYear,
          onProgress: (progressEvent) => {
            if (progressEvent.lengthComputable) {
              const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
              commit('SET_UPLOAD_PROGRESS', { fileId: tempFile.id, progress })
              if (options.onProgress) options.onProgress(progress)
            }
          }
        })
        
        // 更新文件信息
        const uploadedFile = {
          ...tempFile,
          id: result?.data?.[0]?.doc_id || tempFile.id,
          status: 'uploaded',
          parseStatus: 'completed',
          metadata: result?.data?.[0]?.doc_metadata
        }
        
        commit('UPDATE_FILE', { 
          fileId: tempFile.id, 
          updates: uploadedFile
        })
        commit('CLEAR_UPLOAD_PROGRESS', tempFile.id)
        
        return uploadedFile
      } catch (error) {
        console.error('文件上传失败:', error)
        commit('UPDATE_FILE', {
          fileId: tempFile.id,
          updates: { status: 'failed', parseStatus: 'failed' }
        })
        commit('CLEAR_UPLOAD_PROGRESS', tempFile.id)
        throw error
      }
    },
    
    // 批量上传文件（政务功能）
    async batchUploadFiles({ dispatch }, { files, options = {} }) {
      try {
        const totalSize = files.reduce((sum, f) => sum + (f.size || 0), 0) || 1
        let uploadedBytes = 0

        const results = []
        for (const file of files) {
          const res = await dispatch('uploadFile', {
            file,
            options: {
              department: options.department,
              publishYear: options.publishYear,
              onProgress: (percent) => {
                // 估算总体进度（按文件大小权重）
                // 注意：这是简单估算，真实聚合需更复杂跟踪
                uploadedBytes += ((percent / 100) * (file.size || 0))
                const overall = Math.min(100, Math.round((uploadedBytes / totalSize) * 100))
                if (typeof options.onProgress === 'function') options.onProgress(overall)
              }
            }
          })
          results.push(res)
        }
        return results
      } catch (error) {
        console.error('批量上传失败:', error)
        throw error
      } finally {
        // 清理总体进度（不存储在state，仅回调）
      }
    },
    
    // 触发解析
    async triggerParse({ commit }, fileId) {
      try {
        commit('SET_PARSE_STATUS', { fileId, status: 'parsing' })
        
        // TODO: 调用解析API
        // const result = await parseFileAPI(fileId)
        
        // 模拟解析过程
        await new Promise(resolve => setTimeout(resolve, 2000))
        
        commit('SET_PARSE_STATUS', { fileId, status: 'completed' })
        commit('UPDATE_FILE', { 
          fileId, 
          updates: { parseStatus: 'completed' } 
        })
        
      } catch (error) {
        console.error('文件解析失败:', error)
        commit('SET_PARSE_STATUS', { fileId, status: 'failed' })
        commit('UPDATE_FILE', { 
          fileId, 
          updates: { parseStatus: 'failed' } 
        })
        throw error
      }
    },
    
    // 删除文件
    async deleteFile({ commit, dispatch }, payload) {
      try {
        // 兼容传入 string（单docId）或对象（聚合条目，包含 docIds）
        if (typeof payload === 'string') {
          await ingestAPI.deleteDocument(payload)
          commit('REMOVE_FILE', payload)
          commit('CLEAR_UPLOAD_PROGRESS', payload)
        } else if (payload && Array.isArray(payload.docIds)) {
          for (const docId of payload.docIds) {
            try {
              await ingestAPI.deleteDocument(docId)
            } catch (e) {
              // 某些 doc_id 可能已不存在，忽略 404 继续删其他
              // 只在全部尝试后统一刷新
              // console.warn('删除doc失败，忽略继续', docId, e)
            }
          }
          commit('REMOVE_FILE', payload.id)
          commit('CLEAR_UPLOAD_PROGRESS', payload.id)
        }
        // 删除后刷新列表，避免残留
        await dispatch('fetchFiles')
      } catch (error) {
        console.error('删除文件失败:', error)
        throw error
      }
    },
    
    // 搜索文件
    searchFiles({ commit }, keyword) {
      commit('SET_SEARCH_KEYWORD', keyword)
    },
    
    // 设置筛选条件
    setFilterConditions({ commit }, conditions) {
      commit('SET_FILTER_CONDITIONS', conditions)
    },
    
    // 重置筛选条件
    resetFilterConditions({ commit }) {
      commit('RESET_FILTER_CONDITIONS')
    }
  },
  getters: {
    // 获取过滤后的文件列表
    filteredFiles: (state) => {
      let files = [...state.files]
      
      // 搜索关键词筛选
      if (state.searchKeyword) {
        const keyword = state.searchKeyword.toLowerCase()
        files = files.filter(file => 
          file.name.toLowerCase().includes(keyword) ||
          (file.department && file.department.toLowerCase().includes(keyword))
        )
      }
      
      // 文件类型筛选
      if (state.filterConditions.fileType) {
        files = files.filter(file => {
          const fileExt = file.name.split('.').pop()?.toLowerCase()
          return state.filterConditions.fileType.includes(fileExt)
        })
      }
      
      // 解析状态筛选
      if (state.filterConditions.parseStatus) {
        files = files.filter(file => file.parseStatus === state.filterConditions.parseStatus)
      }
      
      // 按上传时间排序
      return files.sort((a, b) => new Date(b.uploadTime) - new Date(a.uploadTime))
    },
    
    // 统计信息
    fileStats: (state) => {
      const total = state.files.length
      const uploaded = state.files.filter(f => f.status === 'uploaded').length
      const parsing = state.files.filter(f => f.parseStatus === 'parsing').length
      const completed = state.files.filter(f => f.parseStatus === 'completed').length
      const failed = state.files.filter(f => f.parseStatus === 'failed').length
      
      return {
        total,
        uploaded,
        parsing,
        completed,
        failed
      }
    }
  }
}

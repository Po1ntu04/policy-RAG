import { chatAPI } from '../../services/api'

export default {
  namespaced: true,
  state: {
    // 聊天消息列表
    messages: [],
    // 当前输入
    currentInput: '',
    // 聊天状态
    chatStatus: 'idle', // idle, typing, loading
    // 上下文过滤器
    contextFilter: null,
    // 智能功能开关
    smartFeaturesEnabled: true,
    // 是否包含来源信息
    includeSources: true,
    systemPrompt: null,
    useDefaultPrompt: true
  },
  mutations: {
    // 添加消息
    ADD_MESSAGE(state, message) {
      state.messages.push({
        ...message,
        id: Date.now() + Math.random(),
        timestamp: new Date().toISOString()
      })
    },
    // 更新最后一条消息
    UPDATE_LAST_MESSAGE(state, updates) {
      if (state.messages.length > 0) {
        const lastIndex = state.messages.length - 1
        state.messages[lastIndex] = {
          ...state.messages[lastIndex],
          ...updates
        }
      }
    },
    // 清空消息
    CLEAR_MESSAGES(state) {
      state.messages = []
    },
    // 设置当前输入
    SET_CURRENT_INPUT(state, input) {
      state.currentInput = input
    },
    // 设置聊天状态
    SET_CHAT_STATUS(state, status) {
      state.chatStatus = status
    },
    // 设置上下文过滤器
    SET_CONTEXT_FILTER(state, filter) {
      state.contextFilter = filter
    },
    // 设置智能功能开关
    SET_SMART_FEATURES(state, enabled) {
      state.smartFeaturesEnabled = enabled
    },
    // 设置来源信息开关
    SET_INCLUDE_SOURCES(state, enabled) {
      state.includeSources = enabled
    },
    SET_SYSTEM_PROMPT(state, prompt) {
      state.systemPrompt = prompt
    },
    SET_USE_DEFAULT_PROMPT(state, enabled) {
      state.useDefaultPrompt = enabled
    }
  },
  actions: {
    // 发送消息
    async sendMessage({ commit, state }, { content, type = 'text' }) {
      try {
        // 添加用户消息
        const userMessage = {
          role: 'user',
          type,
          content,
          status: 'sent'
        }
        commit('ADD_MESSAGE', userMessage)
        commit('SET_CHAT_STATUS', 'loading')

        // 添加助手消息占位符
        const assistantMessage = {
          role: 'assistant',
          type: 'text',
          content: '',
          status: 'typing',
          sources: []
        }
        commit('ADD_MESSAGE', assistantMessage)

        // 构建消息历史
        const messages = state.messages
          .filter(m => m.role && m.status !== 'typing')
          .map(m => ({
            role: m.role,
            content: m.content
          }))

        // 调用后端 /v1/chat/completions（private-gpt 原生接口）
        const response = await chatAPI.completions(messages, {
          useContext: true,
          contextFilter: state.contextFilter,
          includeSources: state.includeSources,
          stream: false,
          systemPrompt: state.systemPrompt,
          useDefaultPrompt: state.useDefaultPrompt
        })

        // 更新助手回答
        commit('UPDATE_LAST_MESSAGE', {
          content: response?.choices?.[0]?.message?.content || '抱歉，我无法回答这个问题。',
          status: 'completed',
          sources: response?.choices?.[0]?.sources || []
        })
        commit('SET_CHAT_STATUS', 'idle')

      } catch (error) {
        console.error('发送消息失败:', error)
        commit('UPDATE_LAST_MESSAGE', {
          status: 'failed',
          content: '抱歉，消息发送失败：' + (error.message || '未知错误')
        })
        commit('SET_CHAT_STATUS', 'idle')
        throw error
      }
    },

    // 重新生成回答
    async regenerateResponse({ state, dispatch }) {
      if (state.messages.length < 2) return

      // 移除最后的助手回答
      const messages = [...state.messages]
      if (messages[messages.length - 1].role === 'assistant') {
        messages.pop()
      }

      // 重新发送最后的用户消息
      const lastUserMessage = messages.reverse().find(m => m.role === 'user')
      if (lastUserMessage) {
        await dispatch('sendMessage', {
          content: lastUserMessage.content,
          type: lastUserMessage.type
        })
      }
    },

    // 停止生成
    stopGeneration({ commit }) {
      commit('SET_CHAT_STATUS', 'idle')
      commit('UPDATE_LAST_MESSAGE', { status: 'stopped' })
    },

    // 清空对话
    clearChat({ commit }) {
      commit('CLEAR_MESSAGES')
      commit('SET_CHAT_STATUS', 'idle')
    },

    // 设置上下文过滤器
    setContextFilter({ commit }, filter) {
      commit('SET_CONTEXT_FILTER', filter)
    },
    setSystemPrompt({ commit }, prompt) {
      commit('SET_SYSTEM_PROMPT', prompt)
      commit('SET_USE_DEFAULT_PROMPT', !prompt)
    },
    clearSystemPrompt({ commit }) {
      commit('SET_SYSTEM_PROMPT', null)
      commit('SET_USE_DEFAULT_PROMPT', true)
    },

    // 切换智能功能
    toggleSmartFeatures({ commit, state }) {
      commit('SET_SMART_FEATURES', !state.smartFeaturesEnabled)
    },

    // 切换来源信息
    toggleIncludeSources({ commit, state }) {
      commit('SET_INCLUDE_SOURCES', !state.includeSources)
    }
  },
  getters: {
    // 最新消息
    lastMessage: (state) => {
      return state.messages[state.messages.length - 1] || null
    },

    // 用户消息数量
    userMessageCount: (state) => {
      return state.messages.filter(m => m.role === 'user').length
    },

    // 是否可以发送消息
    canSendMessage: (state) => {
      return state.chatStatus === 'idle'
    },

    // 是否正在加载
    isLoading: (state) => {
      return state.chatStatus === 'loading'
    }
  }
}

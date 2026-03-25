import api from '../../services/api'

export default {
  namespaced: true,
  state: {
    token: localStorage.getItem('auth_token') || '',
    user: (() => {
      try {
        const raw = localStorage.getItem('auth_user')
        return raw ? JSON.parse(raw) : null
      } catch (e) {
        return null
      }
    })()
  },
  mutations: {
    SET_TOKEN(state, token) {
      state.token = token
    },
    SET_USER(state, user) {
      state.user = user
    },
    CLEAR_AUTH(state) {
      state.token = ''
      state.user = null
    }
  },
  actions: {
    async login({ commit }, { username, password }) {
      const resp = await api.post('/auth/login', { username, password })
      const token = resp?.access_token
      const user = resp?.user
      if (!token || !user) {
        throw new Error('登录失败，请检查用户名或密码')
      }
      localStorage.setItem('auth_token', token)
      localStorage.setItem('auth_user', JSON.stringify(user))
      commit('SET_TOKEN', token)
      commit('SET_USER', user)
      return user
    },
    async fetchMe({ commit }) {
      try {
        const user = await api.get('/auth/me')
        if (user) {
          localStorage.setItem('auth_user', JSON.stringify(user))
          commit('SET_USER', user)
        }
        return user
      } catch (e) {
        return null
      }
    },
    logout({ commit }) {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('auth_user')
      commit('CLEAR_AUTH')
    }
  },
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    displayName: (state) => state.user?.display_name || state.user?.username || '',
    roles: (state) => state.user?.roles || [],
    hasRole: (state, getters) => (role) => getters.roles.includes(role),
    isPublic: (state, getters) => getters.roles.includes('public')
  }
}

import { createStore } from 'vuex'
import fileIngest from './modules/fileIngest'
import chat from './modules/chat'
import table from './modules/table'
import audit from './modules/audit'
import auth from './modules/auth'

export default createStore({
  state: {
    loading: false,
    user: null
  },
  mutations: {
    SET_LOADING(state, loading) {
      state.loading = loading
    },
    SET_USER(state, user) {
      state.user = user
    }
  },
  actions: {
    setLoading({ commit }, loading) {
      commit('SET_LOADING', loading)
    },
    setUser({ commit }, user) {
      commit('SET_USER', user)
    }
  },
  modules: {
    auth,
    fileIngest,
    chat,
    table,
    audit
  }
})

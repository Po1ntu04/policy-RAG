import { createRouter, createWebHistory } from 'vue-router'
import store from '../store'

// 路由组件懒加载
const FileIngest = () => import('../views/FileIngest.vue')
const SmartChat = () => import('../views/SmartChat.vue')
const TableGeneration = () => import('../views/TableGeneration.vue')
const AuditEvaluation = () => import('../views/AuditEvaluation.vue')
const IndicatorsManagement = () => import('../views/IndicatorsManagement.vue')
const PublicDocs = () => import('../views/PublicDocs.vue')
const PublicDocDetail = () => import('../views/PublicDocDetail.vue')
const MyPage = () => import('../views/MyPage.vue')
const Login = () => import('../views/Login.vue')

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: {
      title: '登录',
      public: true,
      hideLayout: true
    }
  },
  {
    path: '/',
    redirect: '/ingest'
  },
  {
    path: '/ingest',
    name: 'FileIngest',
    component: FileIngest,
    meta: {
      title: '文件入库',
      icon: 'upload',
      requiresAuth: true,
      disallowRoles: ['public']
    }
  },
  {
    path: '/public-docs',
    name: 'PublicDocs',
    component: PublicDocs,
    meta: {
      title: '公开文件',
      icon: 'folder-open',
      requiresAuth: true
    }
  },
  {
    path: '/public-docs/:policyId',
    name: 'PublicDocDetail',
    component: PublicDocDetail,
    meta: {
      title: '公开文件详情',
      requiresAuth: true
    }
  },
  {
    path: '/my',
    name: 'MyPage',
    component: MyPage,
    meta: {
      title: '我的',
      requiresAuth: true,
      disallowRoles: ['admin']
    }
  },
  {
    path: '/chat',
    name: 'SmartChat',
    component: SmartChat,
    meta: {
      title: '智能问答',
      icon: 'comment',
      requiresAuth: true
    }
  },
  {
    path: '/indicators',
    name: 'IndicatorsManagement',
    component: IndicatorsManagement,
    meta: {
      title: '指标管理',
      icon: 'ordered-list',
      requiresAuth: true
    }
  },
  {
    path: '/table',
    name: 'TableGeneration',
    component: TableGeneration,
    meta: {
      title: '表格生成',
      icon: 'table',
      requiresAuth: true
    }
  },
  {
    path: '/audit',
    name: 'AuditEvaluation',
    component: AuditEvaluation,
    meta: {
      title: '审计评估',
      icon: 'audit',
      requiresAuth: true
    }
  }
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes
})

// 路由前置守卫
router.beforeEach((to, from, next) => {
  // 设置页面标题
  if (to.meta?.title) {
    document.title = `${to.meta.title} - 政务文档智能处理系统`
  }
  const requiresAuth = to.meta?.requiresAuth
  const isPublic = to.meta?.public
  const isLoggedIn = store.getters['auth/isAuthenticated']
  const roles = store.getters['auth/roles'] || []
  const disallowRoles = to.meta?.disallowRoles || []
  if (requiresAuth && !isLoggedIn) {
    next('/login')
    return
  }
  if (isPublic && isLoggedIn && to.path === '/login') {
    next('/ingest')
    return
  }
  if (disallowRoles.length && roles.some(role => disallowRoles.includes(role))) {
    next('/public-docs')
    return
  }
  next()
})

export default router

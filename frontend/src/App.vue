<template>
  <div id="app">
    <a-config-provider :locale="zhCN">
      <div class="app-layout">
        <!-- 顶部导航栏 -->
        <div class="app-header" v-if="!hideLayout">
          <div class="header-content">
            <div class="logo-section">
              <div class="logo">
                <span class="title">政务文档智能处理系统</span>
              </div>
            </div>

            <div class="nav-section">
              <a-menu v-model:selectedKeys="currentNav" mode="horizontal" theme="light" class="nav-menu">
                <a-menu-item
                  v-if="!isPublic"
                  key="ingest"
                  @click="navigateTo('/ingest')"
                >
                  <template #icon>
                    <upload-outlined />
                  </template>
                  文件入库
                </a-menu-item>
                <a-menu-item key="public-docs" @click="navigateTo('/public-docs')">
                  <template #icon>
                    <folder-open-outlined />
                  </template>
                  公开文件
                </a-menu-item>
                <a-menu-item v-if="!isAdmin" key="my" @click="navigateTo('/my')">
                  <template #icon>
                    <user-outlined />
                  </template>
                  我的
                </a-menu-item>
                <a-menu-item key="chat" @click="navigateTo('/chat')">
                  <template #icon>
                    <comment-outlined />
                  </template>
                  智能问答
                </a-menu-item>
                <a-menu-item key="indicators" @click="navigateTo('/indicators')">
                  <template #icon>
                    <ordered-list-outlined />
                  </template>
                  指标管理
                </a-menu-item>
                <a-menu-item key="table" @click="navigateTo('/table')">
                  <template #icon>
                    <table-outlined />
                  </template>
                  表格生成
                </a-menu-item>
                <a-menu-item key="audit" @click="navigateTo('/audit')">
                  <template #icon>
                    <audit-outlined />
                  </template>
                  审计评估
                </a-menu-item>
              </a-menu>
            </div>

            <div class="user-section">
              <a-dropdown>
                <a-button type="text">
                  <span class="user-name">{{ userDisplay || '用户' }}</span>
                </a-button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item @click="handleLogout">退出登录</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>
          </div>
        </div>

        <!-- 主体内容区域 -->
        <div class="app-main">
          <router-view />
        </div>
      </div>
    </a-config-provider>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStore } from 'vuex'
import {
  UploadOutlined,
  FolderOpenOutlined,
  CommentOutlined,
  TableOutlined,
  AuditOutlined,
  OrderedListOutlined,
  UserOutlined
} from '@ant-design/icons-vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'

export default {
  name: 'App',
  components: {
    UploadOutlined,
    FolderOpenOutlined,
    CommentOutlined,
    TableOutlined,
    AuditOutlined,
    OrderedListOutlined,
    UserOutlined
  },
  setup() {
    const route = useRoute()
    const router = useRouter()
    const store = useStore()
    const currentNav = ref(['ingest'])
    const hideLayout = computed(() => Boolean(route.meta?.hideLayout))
    const userDisplay = computed(() => store.getters['auth/displayName'])
    const isPublic = computed(() => store.getters['auth/isPublic'])
    const isAdmin = computed(() => (store.getters['auth/roles'] || []).includes('admin'))

    // 根据路由更新当前导航
    const updateNavFromRoute = () => {
      const pathToKey = {
        '/ingest': 'ingest',
        '/public-docs': 'public-docs',
        '/my': 'my',
        '/chat': 'chat',
        '/indicators': 'indicators',
        '/table': 'table',
        '/audit': 'audit'
      }

      let key = pathToKey[route.path]
      if (!key && route.path.startsWith('/public-docs/')) {
        key = 'public-docs'
      }
      if (!key && route.path.startsWith('/my')) {
        key = 'my'
      }
      if (!key) {
        key = 'ingest'
      }
      currentNav.value = [key]
    }

    // 导航到指定路由
    const navigateTo = (path) => {
      router.push(path)
    }

    const handleLogout = () => {
      store.dispatch('auth/logout')
      router.push('/login')
    }

    // 监听路由变化
    watch(route, updateNavFromRoute, { immediate: true })

    onMounted(() => {
      updateNavFromRoute()
      if (store.getters['auth/isAuthenticated']) {
        store.dispatch('auth/fetchMe')
      }
    })

    return {
      zhCN,
      currentNav,
      navigateTo,
      hideLayout,
      userDisplay,
      isPublic,
      isAdmin,
      handleLogout
    }
  }
}
</script>

<style lang="less">
#app {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  position: relative;

  .header-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 24px;
  }

  .logo-section {
    .logo {
      display: flex;
      align-items: center;
      gap: 12px;

      img {
        height: 32px;
        width: auto;
      }

      .title {
        font-size: 20px;
        font-weight: 600;
        color: #1890ff;
      }
    }
  }

  .nav-section {
    .nav-menu {
      border-bottom: none;

      .ant-menu-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 16px;

        &:hover,
        &.ant-menu-item-selected {
          color: #1890ff;
        }
      }
    }
  }

  .user-section {
    display: flex;
    align-items: center;
    gap: 8px;

    .user-name {
      color: #595959;
      font-size: 14px;
    }
  }
}

.app-main {
  flex: 1;
  overflow: hidden;
  background: #f0f2f5;
}

// 全局样式重置
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: #f0f2f5;
}
</style>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h2>政务文档智能处理系统</h2>
        <p>登录后使用指标管理、审计评估与数据分析功能</p>
      </div>

      <a-form layout="vertical">
        <a-form-item label="用户名">
          <a-input v-model:value="form.username" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="form.password" placeholder="请输入密码" />
        </a-form-item>
        <a-button type="primary" block :loading="loading" @click="handleLogin">
          登录
        </a-button>
      </a-form>

      <div class="demo-accounts">
        <div class="demo-title">演示账号</div>
        <ul>
          <li>管理员：admin / admin123</li>
          <li>工作人员：staff / staff123</li>
          <li>领导：leader / leader123</li>
          <li>公众：public / public123</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script>
import { reactive, ref } from 'vue'
import { useStore } from 'vuex'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'

export default {
  name: 'LoginView',
  setup() {
    const store = useStore()
    const router = useRouter()
    const loading = ref(false)
    const form = reactive({
      username: '',
      password: ''
    })

    const handleLogin = async () => {
      if (!form.username || !form.password) {
        message.warning('请输入用户名和密码')
        return
      }
      loading.value = true
      try {
        await store.dispatch('auth/login', {
          username: form.username,
          password: form.password
        })
        message.success('登录成功')
        router.push('/ingest')
      } catch (e) {
        message.error(e?.message || '登录失败')
      } finally {
        loading.value = false
      }
    }

    return {
      form,
      loading,
      handleLogin
    }
  }
}
</script>

<style lang="less" scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f0f5ff 0%, #ffffff 100%);
}

.login-card {
  width: 420px;
  background: #fff;
  border-radius: 10px;
  padding: 28px 32px;
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.08);
}

.login-header {
  text-align: center;
  margin-bottom: 20px;

  h2 {
    margin: 0 0 6px 0;
    font-size: 20px;
    color: #1f1f1f;
  }

  p {
    margin: 0;
    color: #8c8c8c;
    font-size: 13px;
  }
}

.demo-accounts {
  margin-top: 18px;
  background: #fafafa;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  color: #595959;

  .demo-title {
    font-weight: 600;
    margin-bottom: 6px;
  }

  ul {
    margin: 0;
    padding-left: 18px;
  }
}
</style>

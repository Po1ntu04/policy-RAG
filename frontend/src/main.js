import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'

// Ant Design Vue
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'

// 可在此处引入自定义样式文件

// 创建Vue应用
const app = createApp(App)

// 规避浏览器 ResizeObserver 的已知噪声报错（不影响功能，但会在控制台刷屏）
if (typeof window !== 'undefined') {
    window.addEventListener('error', (event) => {
        const message = String(event?.message || '')
        if (
            message.includes('ResizeObserver loop limit exceeded') ||
            message.includes('ResizeObserver loop completed with undelivered notifications')
        ) {
            event.stopImmediatePropagation()
        }
    })
}

// 安装插件
app.use(store)
app.use(router)
app.use(Antd)

// 全局配置
app.config.productionTip = false

// 挂载应用
app.mount('#app')